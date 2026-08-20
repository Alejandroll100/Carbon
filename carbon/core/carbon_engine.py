"""Orquestrador do GEØ.IA Carbon Engine.

Separação de estágios obrigatória:

    observação -> extração de pool -> agregação de estoque -> mudança ->
    remoção -> balanço -> qualidade -> insights

Nenhuma etapa posterior altera dado de etapa anterior. Nenhum ``None`` vira
zero em nenhum agregador.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Optional, Sequence

from pydantic import BaseModel

from ..factors.registry import FactorRegistry
from ..models.enums import (
    CalculationMode,
    CarbonPool,
    EstimationType,
    ResultStatus,
)
from ..models.inventory import CarbonInventory, OperationalEmissionEntry
from ..models.land import LandEvent
from ..models.project import CarbonProject
from ..models.provenance import TracedValue
from ..models.result import (
    AuditRecord,
    CarbonResult,
    CarbonStockResult,
    PoolResult,
)
from ..services.factor_service import FactorResolver, ProjectParameter, ProxyAuthorization
from ..services.inventory_service import aboveground_from_plots, equation_audit
from ..services.report_service import build_insights
from ..utils.conversions import carbon_to_co2e, per_hectare
from ..version import ENGINE_VERSION, METHODOLOGY_VERSION
from . import biomass_engine, change_engine, confidence_engine, removal_engine, soil_engine
from .sanity import run_sanity_checks
from .uncertainty_engine import combine_sum

METHODOLOGY_FRAMEWORK = [
    "IPCC 2006 Guidelines for National Greenhouse Gas Inventories, Volume 4 (AFOLU)",
    "IPCC 2019 Refinement to the 2006 Guidelines",
    "GHG Protocol Land Sector and Removals Standard (princípios aplicáveis)",
]


class CarbonEngineConfig(BaseModel):
    #: Modo científico estrito: recusa fator não validado, fonte ausente,
    #: unidade incompatível, equação não validada e proxy.
    strict_factor_validation: bool = False
    #: No modo estrito o padrão passa a ser False, independentemente daqui.
    allow_scientific_proxy: bool = True
    #: Permite estimar AGB por densidade default (caminho do quick_estimate).
    allow_default_biomass_density: bool = True
    default_equation_id: Optional[str] = None
    default_wood_density_g_cm3: Optional[float] = None
    #: Proxy autorizado para razão raiz:parte aérea (ex.: classe análoga do IPCC).
    root_to_shoot_proxy: Optional[ProxyAuthorization] = None


class CarbonEngine:
    def __init__(
        self,
        registry: Optional[FactorRegistry] = None,
        config: Optional[CarbonEngineConfig] = None,
    ) -> None:
        self.registry = registry or FactorRegistry.load_default()
        self.config = config or CarbonEngineConfig()

    # -- estágio 1-3: estoque --------------------------------------------------
    def compute_stock(
        self,
        project: CarbonProject,
        inventory: CarbonInventory,
        resolver: FactorResolver,
    ) -> tuple[CarbonStockResult, list[str]]:
        missing: list[str] = []
        pools: dict[str, PoolResult] = {}

        plot_derived: Optional[TracedValue] = None
        if inventory.plots:
            plot_derived = aboveground_from_plots(
                project,
                inventory.plots,
                default_equation_id=self.config.default_equation_id,
                default_wood_density=self.config.default_wood_density_g_cm3,
            )
            if not plot_derived.available:
                missing.append(
                    f"tree_inventory: {plot_derived.notes[0] if plot_derived.notes else 'indisponível'}"
                )

        agb = biomass_engine.aboveground_estimate(
            project,
            inventory,
            resolver,
            plot_derived=plot_derived,
            allow_default_density=self.config.allow_default_biomass_density,
        )
        pools[CarbonPool.ABOVEGROUND.value] = self._to_pool_result(
            CarbonPool.ABOVEGROUND, agb, inventory, project, resolver
        )
        if not pools[CarbonPool.ABOVEGROUND.value].available:
            missing.append("aboveground_biomass")

        bgb = biomass_engine.belowground_estimate(
            project,
            agb.dry_biomass,
            inventory.belowground,
            resolver,
            proxy=self.config.root_to_shoot_proxy,
        )
        pools[CarbonPool.BELOWGROUND.value] = self._to_pool_result(
            CarbonPool.BELOWGROUND, bgb, inventory, project, resolver
        )
        if not pools[CarbonPool.BELOWGROUND.value].available:
            missing.append("belowground_biomass")

        for pool, obs in (
            (CarbonPool.DEADWOOD, inventory.deadwood),
            (CarbonPool.LITTER, inventory.litter),
        ):
            estimate = biomass_engine.dead_organic_matter_estimate(
                project, obs, pool.value, resolver
            )
            pools[pool.value] = self._to_pool_result(pool, estimate, inventory, project, resolver)
            if not pools[pool.value].available:
                missing.append(pool.value)

        soil_carbon = soil_engine.compute_soil_carbon(project, inventory.soil, resolver)
        pools[CarbonPool.SOIL.value] = self._carbon_only_pool(
            CarbonPool.SOIL, soil_carbon, project.area_ha
        )
        if not pools[CarbonPool.SOIL.value].available:
            missing.append("soil_organic_carbon")

        available = [name for name, p in pools.items() if p.available]
        unavailable = [name for name, p in pools.items() if not p.available]

        total_c: Optional[float] = None
        total_co2: Optional[float] = None
        c_ha: Optional[float] = None
        co2_ha: Optional[float] = None
        if available:
            total_c = sum(pools[n].carbon_t.value for n in available)  # type: ignore[misc]
            total_co2 = carbon_to_co2e(total_c)
            c_ha = per_hectare(total_c, project.area_ha)
            co2_ha = per_hectare(total_co2, project.area_ha)

        uncertainty = combine_sum(
            (n, pools[n].carbon_t.value, pools[n].carbon_t.uncertainty_percent)  # type: ignore[arg-type]
            for n in available
        )

        stock = CarbonStockResult(
            inventory_id=inventory.inventory_id,
            year=inventory.year,
            area_ha=project.area_ha,
            pools=pools,
            total_carbon_t=total_c,
            total_co2e_t=total_co2,
            carbon_t_ha=c_ha,
            co2e_t_ha=co2_ha,
            available_pools=available,
            missing_pools=unavailable,
            uncertainty=uncertainty,
            status=ResultStatus.COMPLETE
            if not unavailable
            else (ResultStatus.PARTIAL if available else ResultStatus.FAILED),
        )
        return stock, missing

    # -- pipeline completo -----------------------------------------------------
    def calculate(
        self,
        project: CarbonProject,
        inventory: CarbonInventory,
        *,
        baseline_inventory: Optional[CarbonInventory] = None,
        events: Optional[Sequence[LandEvent]] = None,
        operational_emissions: Optional[Sequence[OperationalEmissionEntry]] = None,
        mode: Optional[CalculationMode] = None,
        project_parameters: Optional[dict[str, ProjectParameter]] = None,
    ) -> CarbonResult:
        mode = mode or inventory.mode
        resolver = FactorResolver(
            self.registry,
            project_parameters=project_parameters,
            strict_factor_validation=self.config.strict_factor_validation,
            allow_scientific_proxy=self.config.allow_scientific_proxy,
        )

        current_stock, missing = self.compute_stock(project, inventory, resolver)

        baseline_stock = None
        change = None
        removal = None
        if baseline_inventory is not None:
            baseline_stock, baseline_missing = self.compute_stock(
                project, baseline_inventory, resolver
            )
            missing.extend(f"baseline::{m}" for m in baseline_missing)
            change = change_engine.compute_stock_change(
                baseline_stock,
                current_stock,
                baseline_year=baseline_inventory.year,
                current_year=inventory.year,
            )
            removal = removal_engine.compute_removal(change, area_ha=project.area_ha)
        else:
            missing.append("baseline_inventory")

        losses = removal_engine.compute_losses(list(events or []))
        ops = removal_engine.compute_operational_emissions(
            list(operational_emissions or []), resolver
        )
        net = removal_engine.compute_net_balance(removal, losses, ops)
        quality = confidence_engine.compute_confidence(current_stock, resolver, change=change)

        equations = [
            e for p in current_stock.pools.values() for e in p.carbon_t.equations_used
        ]

        audit = AuditRecord(
            calculation_id=str(uuid.uuid4()),
            engine_version=ENGINE_VERSION,
            factor_database_version=self.registry.version,
            methodology_version=METHODOLOGY_VERSION,
            calculation_mode=mode,
            input_fingerprint=self._fingerprint(project, inventory, baseline_inventory),
            input_snapshot={
                "project": json.loads(project.model_dump_json()),
                "inventory": json.loads(inventory.model_dump_json()),
                "baseline_inventory": json.loads(baseline_inventory.model_dump_json())
                if baseline_inventory
                else None,
                "events": [json.loads(e.model_dump_json()) for e in (events or [])],
                "operational_emissions": [
                    json.loads(o.model_dump_json()) for o in (operational_emissions or [])
                ],
            },
            factors_used=resolver.audit_trail(),
            equations_used=equation_audit(equations),
            resolution_traces=resolver.resolution_traces(),
            reference_database_version=self.registry.references.version,
            strict_factor_validation=self.config.strict_factor_validation,
            allow_scientific_proxy=resolver.allow_proxy,
            warnings=resolver.warnings,
        )

        status = (
            ResultStatus.COMPLETE
            if not missing and current_stock.status == ResultStatus.COMPLETE
            else ResultStatus.PARTIAL
            if current_stock.available_pools
            else ResultStatus.FAILED
        )

        result = CarbonResult(
            project_id=project.project_id,
            area_ha=project.area_ha,
            land_use=project.land_use.value,
            calculation_mode=mode,
            status=status,
            carbon_stock=current_stock,
            baseline_stock=baseline_stock,
            change=change,
            removal=removal,
            losses=losses,
            operational_emissions=ops,
            net_balance=net,
            quality=quality,
            missing_data=sorted(set(missing)),
            unresolved_factors=resolver.unresolved,
            proxy_used=resolver.used_proxy,
            validation_warnings=resolver.warnings + list(dict.fromkeys(
                note
                for p in current_stock.pools.values()
                for note in p.carbon_t.notes
                if "REQUIRES_VALIDATION" in note
            )),
            methodology={
                "framework": METHODOLOGY_FRAMEWORK,
                "implemented_scope": [
                    "Carbon Inventory",
                    "Carbon Stock Estimate",
                    "Carbon Removal Estimate",
                ],
                "not_implemented": ["Carbon Credit Potential", "Verified Carbon Credits"],
                "engine_version": ENGINE_VERSION,
                "factor_database_version": self.registry.version,
                "methodology_version": METHODOLOGY_VERSION,
            },
            audit=audit,
        )
        result.sanity_findings = [f.model_dump() for f in run_sanity_checks(result)]
        result.insights = build_insights(result)
        return result

    # -- helpers ---------------------------------------------------------------
    def _to_pool_result(
        self,
        pool: CarbonPool,
        estimate: "biomass_engine.PoolEstimate",
        inventory: CarbonInventory,
        project: CarbonProject,
        resolver: FactorResolver,
    ) -> PoolResult:
        # Caminho 1: o fator/medição já entregou carbono.
        if estimate.carbon is not None:
            return self._carbon_only_pool(pool, estimate.carbon, project.area_ha)

        biomass = estimate.dry_biomass
        if biomass is None or not biomass.available:
            reason = (
                biomass.notes[0]
                if biomass is not None and biomass.notes
                else "biomassa indisponível"
            )
            return PoolResult(
                pool=pool,
                dry_biomass_t=biomass,
                carbon_t=TracedValue.not_available("tC", reason),
            )

        # Caminho 2: aplicar fração de carbono do pool + uso da terra.
        try:
            fraction = biomass_engine.resolve_carbon_fraction(
                inventory, project, resolver, purpose=pool.value, pool=pool.value
            )
        except Exception as exc:
            return PoolResult(
                pool=pool,
                dry_biomass_t=biomass,
                carbon_t=TracedValue.not_available(
                    "tC", f"Fração de carbono não resolvida para {pool.value}: {exc}"
                ),
            )

        carbon = biomass_engine.biomass_to_carbon(
            biomass.value, fraction, pool=pool.value, biomass_provenance=biomass  # type: ignore[arg-type]
        )
        return self._carbon_only_pool(pool, carbon, project.area_ha, biomass=biomass)

    @staticmethod
    def _carbon_only_pool(
        pool: CarbonPool,
        carbon: TracedValue,
        area_ha: float,
        *,
        biomass: Optional[TracedValue] = None,
    ) -> PoolResult:
        if not carbon.available:
            return PoolResult(pool=pool, dry_biomass_t=biomass, carbon_t=carbon)
        co2 = carbon_to_co2e(carbon.value)  # type: ignore[arg-type]
        from .uncertainty_engine import combine_product

        return PoolResult(
            pool=pool,
            dry_biomass_t=biomass,
            carbon_t=carbon,
            co2e_t=co2,
            carbon_t_ha=per_hectare(carbon.value, area_ha),  # type: ignore[arg-type]
            co2e_t_ha=per_hectare(co2, area_ha),
            uncertainty=combine_product(carbon.value, [carbon.uncertainty_percent]),  # type: ignore[arg-type]
        )

    @staticmethod
    def _fingerprint(
        project: CarbonProject,
        inventory: CarbonInventory,
        baseline: Optional[CarbonInventory],
    ) -> str:
        payload = {
            "project": json.loads(project.model_dump_json()),
            "inventory": json.loads(inventory.model_dump_json()),
            "baseline": json.loads(baseline.model_dump_json()) if baseline else None,
        }
        # created_at não entra no fingerprint: não altera o resultado numérico.
        for key in ("project", "inventory", "baseline"):
            if isinstance(payload[key], dict):
                payload[key].pop("created_at", None)
        blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()
