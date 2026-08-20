"""Motor de biomassa: AGB, BGB e conversão biomassa -> carbono.

Regras:

* nenhuma razão raiz:parte aérea hardcoded;
* a fração de carbono nunca é escondida e é escolhida por POOL e por USO DA
  TERRA (o IPCC usa 0,47 em floresta, 0,50 em cropland, 0,40/0,37 em
  serapilheira, 0,50 em madeira morta — o motor não uniformiza);
* biomassa ausente é ``not_available``, jamais zero;
* alguns fatores default entregam CARBONO direto (Tabela 5.1), outros entregam
  MATÉRIA SECA (Tabela 5.2). O motor mantém a distinção e só aplica fração de
  carbono onde ela cabe.
"""

from __future__ import annotations

import math
from typing import Optional

from pydantic import BaseModel

from ..factors.registry import FactorNotFoundError
from ..models.enums import DataLevel, EstimationType, LandUse, ValidationStatus
from ..models.inventory import BelowgroundObservation, BiomassObservation, CarbonInventory
from ..models.project import CarbonProject
from ..models.provenance import TracedValue
from ..services.factor_service import (
    FactorResolution,
    FactorResolver,
    ProxyAuthorization,
    ResolutionTrace,
)

DRY_MATTER_UNIT = "t dry matter"
CARBON_UNIT = "tC"
CARBON_FRACTION_UNIT = "tC/t d.m."

#: Regimes de temperatura/umidade usados pelas Tabelas 5.1 e 5.9, derivados da
#: região climática do IPCC.
CLIMATE_REGION_TO_TABLE51 = {
    "tropical_dry": ("tropical", "dry"),
    "tropical_moist": ("tropical", "moist"),
    "tropical_wet": ("tropical", "wet"),
    "tropical_montane": ("tropical", "moist"),
    "warm_temperate_dry": ("temperate", None),
    "warm_temperate_moist": ("temperate", None),
    "cold_temperate_dry": ("temperate", None),
    "cold_temperate_moist": ("temperate", None),
    "boreal": ("temperate", None),
}


class PoolEstimate(BaseModel):
    """Estimativa de um pool: matéria seca, carbono, ou nenhum dos dois.

    Quando ``carbon`` já vem preenchido, a fração de carbono NÃO é aplicada —
    o fator de origem já entregou carbono.
    """

    dry_biomass: Optional[TracedValue] = None
    carbon: Optional[TracedValue] = None

    @property
    def available(self) -> bool:
        return (self.dry_biomass is not None and self.dry_biomass.available) or (
            self.carbon is not None and self.carbon.available
        )

    @classmethod
    def unavailable(cls, reason: str) -> "PoolEstimate":
        return cls(dry_biomass=TracedValue.not_available(DRY_MATTER_UNIT, reason))


# ---------------------------------------------------------------------------
# fração de carbono
# ---------------------------------------------------------------------------

def resolve_carbon_fraction(
    inventory: CarbonInventory,
    project: CarbonProject,
    resolver: FactorResolver,
    *,
    purpose: str = "aboveground biomass",
    pool: str = "aboveground_biomass",
) -> FactorResolution:
    """Hierarquia: override do inventário > parâmetro do projeto > registro."""
    if inventory.carbon_fraction_override is not None:
        return resolver.register_direct(
            FactorResolution(
                factor_id="PROJECT::carbon_fraction",
                category="carbon_fraction",
                value=inventory.carbon_fraction_override,
                unit=CARBON_FRACTION_UNIT,
                pool=pool,
                data_level=DataLevel.PROJECT_SPECIFIC,
                tier=2,
                source_citation=inventory.carbon_fraction_source or "project_input",
                methodology="project_specific_parameter",
                validation_status=ValidationStatus.PROJECT_SUPPLIED,
                trace=ResolutionTrace(
                    requested={"category": "carbon_fraction", "pool": pool},
                    selected_factor="PROJECT::carbon_fraction",
                    selection_reason="Fração de carbono medida/declarada pelo projeto.",
                    data_level=DataLevel.PROJECT_SPECIFIC,
                    resolved=True,
                ),
            )
        )
    return resolver.resolve(
        "carbon_fraction",
        purpose=purpose,
        expected_unit=CARBON_FRACTION_UNIT,
        pool=pool,
        land_use=project.land_use.value,
    )


def biomass_to_carbon(
    dry_biomass_t: float,
    carbon_fraction: FactorResolution,
    *,
    pool: str,
    biomass_provenance: TracedValue,
) -> TracedValue:
    """Carbon = Dry Biomass x Carbon Fraction. O fator sempre volta junto."""
    carbon_t = dry_biomass_t * carbon_fraction.value
    if (
        biomass_provenance.uncertainty_percent is not None
        and carbon_fraction.uncertainty_percent is not None
    ):
        combined = math.sqrt(
            biomass_provenance.uncertainty_percent**2 + carbon_fraction.uncertainty_percent**2
        )
    else:
        combined = biomass_provenance.uncertainty_percent
    return TracedValue(
        value=carbon_t,
        unit=CARBON_UNIT,
        estimation_type=biomass_provenance.estimation_type,
        data_level=carbon_fraction.data_level,
        source=biomass_provenance.source,
        tier=max(carbon_fraction.tier, biomass_provenance.tier or 1),
        uncertainty_percent=combined,
        factors_used=[*biomass_provenance.factors_used, carbon_fraction.factor_id],
        equations_used=[
            *biomass_provenance.equations_used,
            "carbon = dry_biomass * carbon_fraction",
        ],
        inputs={
            "pool": pool,
            "dry_biomass_t": dry_biomass_t,
            "carbon_fraction": carbon_fraction.value,
            "carbon_fraction_factor_id": carbon_fraction.factor_id,
        },
        notes=list(biomass_provenance.notes),
    )


# ---------------------------------------------------------------------------
# AGB
# ---------------------------------------------------------------------------

def aboveground_estimate(
    project: CarbonProject,
    inventory: CarbonInventory,
    resolver: FactorResolver,
    *,
    plot_derived: Optional[TracedValue] = None,
    allow_default_density: bool = True,
) -> PoolEstimate:
    """AGB por ordem de precedência.

    inventário de parcelas > medição direta > densidade default (quick_estimate).
    """
    obs = inventory.aboveground

    if plot_derived is not None and plot_derived.available:
        return PoolEstimate(dry_biomass=plot_derived)

    if obs is not None and obs.carbon_t is not None:
        return PoolEstimate(
            carbon=TracedValue(
                value=obs.carbon_t,
                unit=CARBON_UNIT,
                estimation_type=obs.estimation_type,
                data_level=DataLevel.MEASURED,
                source=obs.source or "field_observation",
                tier=3,
                uncertainty_percent=obs.uncertainty_percent,
                inputs={"carbon_t": obs.carbon_t},
                notes=["Carbono informado diretamente — fração de carbono não aplicada."],
            )
        )

    if obs is not None and obs.dry_biomass_t is not None:
        return PoolEstimate(dry_biomass=_measured(obs, obs.dry_biomass_t, {"dry_biomass_t": obs.dry_biomass_t}))

    if obs is not None and obs.dry_biomass_t_ha is not None:
        total = obs.dry_biomass_t_ha * project.area_ha
        tv = _measured(
            obs,
            total,
            {"dry_biomass_t_ha": obs.dry_biomass_t_ha, "area_ha": project.area_ha},
            equations=["AGB_total = AGB_density * area"],
        )
        return PoolEstimate(dry_biomass=tv)

    if not allow_default_density:
        return PoolEstimate.unavailable(
            "AGB indisponível: sem medição e uso de densidade default desabilitado."
        )

    return _default_density_estimate(project, resolver)


def _measured(
    obs: BiomassObservation,
    value: float,
    inputs: dict,
    *,
    equations: Optional[list[str]] = None,
) -> TracedValue:
    return TracedValue(
        value=value,
        unit=DRY_MATTER_UNIT,
        estimation_type=obs.estimation_type,
        data_level=DataLevel.MEASURED
        if obs.estimation_type == EstimationType.MEASURED
        else DataLevel.PROJECT_SPECIFIC,
        source=obs.source or "field_observation",
        tier=3 if obs.estimation_type == EstimationType.MEASURED else 2,
        uncertainty_percent=obs.uncertainty_percent,
        equations_used=equations or [],
        inputs=inputs,
    )


def _default_density_estimate(project: CarbonProject, resolver: FactorResolver) -> PoolEstimate:
    """Densidade default por hectare (Tier 1) — caminho do ``quick_estimate``.

    Duas famílias de fatores, com unidades diferentes:

    * ``agb_biomass_density``  → t matéria seca/ha (Tabela 5.2, regional)
    * ``agb_carbon_density``   → tC/ha (Tabela 5.1, por regime climático)

    A regional tem prioridade na hierarquia de dados.
    """
    temperature_regime = moisture_regime = None
    if project.climate_region is not None:
        temperature_regime, moisture_regime = CLIMATE_REGION_TO_TABLE51[
            project.climate_region.value
        ]

    # 1. densidade de matéria seca por zona ecológica / região
    regional = resolver.try_resolve(
        "agb_biomass_density",
        purpose="AGB default (densidade de biomassa por zona/região)",
        expected_unit="t d.m./ha",
        land_use=project.land_use.value,
        region=project.region,
        ecological_zone=project.ecological_zone,
        continent=project.continent,
        status_condition=project.forest_status,
        origin=project.forest_origin,
        species=project.species,
    )
    if regional is not None:
        total = regional.value * project.area_ha
        return PoolEstimate(
            dry_biomass=TracedValue(
                value=total,
                unit=DRY_MATTER_UNIT,
                estimation_type=EstimationType.DEFAULT_FACTOR,
                data_level=regional.data_level,
                source=regional.source_citation or regional.reference_id,
                tier=regional.tier,
                uncertainty_percent=regional.uncertainty_percent,
                factors_used=[regional.factor_id],
                equations_used=["AGB_total = AGB_density_default * area"],
                inputs={"agb_density_t_dm_ha": regional.value, "area_ha": project.area_ha},
                notes=["estimated_from_default_factor"],
            )
        )

    # 2. estoque de carbono aéreo default por regime climático
    carbon_density = resolver.try_resolve(
        "agb_carbon_density",
        purpose="AGB default (estoque de carbono por regime climático)",
        expected_unit="tC/ha",
        land_use=project.land_use.value,
        temperature_regime=temperature_regime,
        moisture_regime=moisture_regime,
    )
    if carbon_density is not None:
        total_c = carbon_density.value * project.area_ha
        return PoolEstimate(
            carbon=TracedValue(
                value=total_c,
                unit=CARBON_UNIT,
                estimation_type=EstimationType.DEFAULT_FACTOR,
                data_level=carbon_density.data_level,
                source=carbon_density.source_citation or carbon_density.reference_id,
                tier=carbon_density.tier,
                uncertainty_percent=carbon_density.uncertainty_percent,
                factors_used=[carbon_density.factor_id],
                equations_used=["AGB_C_total = AGB_C_density_default * area"],
                inputs={"agb_carbon_density_tC_ha": carbon_density.value, "area_ha": project.area_ha},
                notes=[
                    "estimated_from_default_factor",
                    "Fator entrega CARBONO diretamente; fração de carbono não aplicada.",
                    carbon_density.trace.selection_reason,
                ],
            )
        )

    return PoolEstimate.unavailable(
        "AGB indisponível: sem medição e sem fator de densidade default aplicável ao "
        f"uso da terra '{project.land_use.value}' e à região climática declarada."
    )


# ---------------------------------------------------------------------------
# BGB
# ---------------------------------------------------------------------------

def belowground_estimate(
    project: CarbonProject,
    agb_dry_biomass: Optional[TracedValue],
    obs: Optional[BelowgroundObservation],
    resolver: FactorResolver,
    *,
    proxy: Optional[ProxyAuthorization] = None,
) -> PoolEstimate:
    """BGB medida, ou BGB = AGB x razão raiz:parte aérea."""
    if obs is not None and obs.dry_biomass_t is not None:
        return PoolEstimate(dry_biomass=_measured(obs, obs.dry_biomass_t, {"dry_biomass_t": obs.dry_biomass_t}))

    if obs is not None and obs.dry_biomass_t_ha is not None:
        total = obs.dry_biomass_t_ha * project.area_ha
        return PoolEstimate(
            dry_biomass=_measured(
                obs,
                total,
                {"dry_biomass_t_ha": obs.dry_biomass_t_ha, "area_ha": project.area_ha},
                equations=["BGB_total = BGB_density * area"],
            )
        )

    if agb_dry_biomass is None or not agb_dry_biomass.available:
        return PoolEstimate.unavailable(
            "BGB indisponível: sem medição e sem AGB em matéria seca para aplicar a razão "
            "raiz:parte aérea. (Fatores que entregam carbono direto não permitem aplicar R.)"
        )

    if obs is not None and obs.root_to_shoot_ratio is not None:
        ratio = resolver.register_direct(
            FactorResolution(
                factor_id="PROJECT::root_to_shoot_ratio",
                category="root_to_shoot_ratio",
                value=obs.root_to_shoot_ratio,
                unit="t BGB / t AGB",
                pool="belowground_biomass",
                data_level=DataLevel.PROJECT_SPECIFIC,
                tier=2,
                source_citation=obs.root_to_shoot_source or "project_input",
                methodology="project_specific_parameter",
                validation_status=ValidationStatus.PROJECT_SUPPLIED,
                uncertainty_percent=obs.root_to_shoot_uncertainty_percent,
                trace=ResolutionTrace(
                    requested={"category": "root_to_shoot_ratio"},
                    selected_factor="PROJECT::root_to_shoot_ratio",
                    selection_reason="Razão raiz:parte aérea fornecida pelo projeto.",
                    data_level=DataLevel.PROJECT_SPECIFIC,
                    resolved=True,
                ),
            )
        )
    else:
        # A Tabela 4.4 (Updated) de 2019 estratifica R por zona ecológica,
        # continente, origem (natural/plantada) e faixa de AGB com limiar de
        # 125 t/ha. A densidade de AGB tem de ser calculada ANTES de resolver R.
        agb_t_ha = agb_dry_biomass.value / project.area_ha  # type: ignore[operator]
        try:
            ratio = resolver.resolve(
                "root_to_shoot_ratio",
                purpose="BGB (razão raiz:parte aérea)",
                expected_unit="t BGB / t AGB",
                land_use=project.land_use.value,
                agb_t_ha=agb_t_ha,
                ecological_zone=project.ecological_zone,
                continent=project.continent,
                origin=project.forest_origin,
                proxy=proxy,
            )
        except Exception as exc:  # FactorNotFoundError / ProxyNotAuthorizedError
            return PoolEstimate.unavailable(f"BGB indisponível: {exc}")

    total = agb_dry_biomass.value * ratio.value  # type: ignore[operator]
    if (
        agb_dry_biomass.uncertainty_percent is not None
        and ratio.uncertainty_percent is not None
    ):
        combined = math.sqrt(
            agb_dry_biomass.uncertainty_percent**2 + ratio.uncertainty_percent**2
        )
    else:
        combined = None

    notes = ["BGB derivada de AGB — não é medição direta de raízes."]
    if combined is None:
        notes.append(
            "Incerteza da BGB não reportada: razão raiz:parte aérea ou AGB sem incerteza declarada."
        )
    if ratio.proxy:
        notes.append(f"PROXY: {ratio.proxy_description}")

    return PoolEstimate(
        dry_biomass=TracedValue(
            value=total,
            unit=DRY_MATTER_UNIT,
            estimation_type=EstimationType.ESTIMATED
            if ratio.data_level == DataLevel.PROJECT_SPECIFIC
            else EstimationType.DEFAULT_FACTOR,
            data_level=ratio.data_level,
            source=ratio.source_citation or ratio.reference_id,
            tier=ratio.tier,
            uncertainty_percent=combined,
            factors_used=[*agb_dry_biomass.factors_used, ratio.factor_id],
            equations_used=["BGB = AGB * root_to_shoot_ratio"],
            inputs={"agb_t": agb_dry_biomass.value, "root_to_shoot_ratio": ratio.value},
            notes=notes,
        )
    )


# ---------------------------------------------------------------------------
# madeira morta e serapilheira
# ---------------------------------------------------------------------------

def dead_organic_matter_estimate(
    project: CarbonProject,
    obs: Optional[BiomassObservation],
    pool_name: str,
    resolver: FactorResolver,
) -> PoolEstimate:
    """Medição direta; se ausente, tenta estoque default (só serapilheira florestal)."""
    if obs is not None and obs.carbon_t is not None:
        return PoolEstimate(
            carbon=TracedValue(
                value=obs.carbon_t,
                unit=CARBON_UNIT,
                estimation_type=obs.estimation_type,
                data_level=DataLevel.MEASURED,
                source=obs.source or "field_observation",
                tier=3,
                uncertainty_percent=obs.uncertainty_percent,
                inputs={"carbon_t": obs.carbon_t},
            )
        )
    if obs is not None and not obs.is_empty:
        if obs.dry_biomass_t is not None:
            return PoolEstimate(
                dry_biomass=_measured(obs, obs.dry_biomass_t, {"dry_biomass_t": obs.dry_biomass_t})
            )
        total = obs.dry_biomass_t_ha * project.area_ha  # type: ignore[operator]
        return PoolEstimate(
            dry_biomass=_measured(
                obs,
                total,
                {"dry_biomass_t_ha": obs.dry_biomass_t_ha, "area_ha": project.area_ha},
                equations=[f"{pool_name}_total = density * area"],
            )
        )

    category = "litter_carbon_stock" if pool_name == "litter" else "deadwood_carbon_stock"
    temperature_regime = None
    if project.climate_region is not None:
        temperature_regime, _ = CLIMATE_REGION_TO_TABLE51[project.climate_region.value]
    default = resolver.try_resolve(
        category,
        purpose=f"{pool_name} (estoque default Tier 1)",
        expected_unit="tC/ha",
        land_use=project.land_use.value,
        temperature_regime=temperature_regime,
        forest_type=project.forest_type,
    )
    if default is None:
        return PoolEstimate.unavailable(
            f"{pool_name}: sem medição e sem estoque default aplicável. "
            f"(Ver base de fatores: para madeira morta o IPCC declara ausência de default.)"
        )
    total_c = default.value * project.area_ha
    return PoolEstimate(
        carbon=TracedValue(
            value=total_c,
            unit=CARBON_UNIT,
            estimation_type=EstimationType.DEFAULT_FACTOR,
            data_level=default.data_level,
            source=default.source_citation or default.reference_id,
            tier=default.tier,
            uncertainty_percent=default.uncertainty_percent,
            factors_used=[default.factor_id],
            equations_used=[f"{pool_name}_C_total = default_stock * area"],
            inputs={"default_stock_tC_ha": default.value, "area_ha": project.area_ha},
            notes=["estimated_from_default_factor", "Fator entrega carbono diretamente."],
        )
    )
