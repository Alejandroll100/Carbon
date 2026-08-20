"""Motor de carbono orgânico do solo (SOC).

Dois caminhos, nunca misturados, sempre identificados na saída:

**A. SOC medido** (``estimation_type: measured``)

    SOC [tC/ha] = BD [g/cm3] x depth [cm] x OC [%] x (1 - coarse_fragment)

Derivação (unidades explícitas):

    massa de solo/ha = BD [t/m3] x 10 000 [m2/ha] x (depth_cm/100) [m]
                     = BD x 100 x depth_cm   [t/ha]
    carbono          = massa x (OC/100) = BD x depth_cm x OC   [tC/ha]

(1 g/cm3 = 1 t/m3, identidade exata.)

**B. SOC Tier 1 do IPCC** (``estimation_type: default_factor``)

    SOC = SOC_REF(região climática, tipo de solo) x F_LU x F_MG x F_I x área

Fonte: IPCC 2006 Vol.4 Cap.2, Equação 2.25 e Tabela 2.3; fatores de mudança de
estoque na Tabela 5.5 do Cap.5. Profundidade de referência: 0-30 cm. Período de
referência dos fatores: D = 20 anos.

O caminho B estima o estoque de EQUILÍBRIO sob o manejo declarado, não o
estoque atual de uma área específica. A saída diz isso explicitamente.
"""

from __future__ import annotations

from typing import Optional

from ..models.enums import (
    CLIMATE_REGION_TO_REGIME,
    CarbonInputLevel,
    CroplandSystem,
    DataLevel,
    EstimationType,
    LandUse,
    TillageManagement,
    ValidationStatus,
)
from ..models.inventory import SoilObservation
from ..models.project import CarbonProject
from ..models.provenance import TracedValue
from ..factors.registry import FactorNotFoundError
from ..services.factor_service import FactorResolution, FactorResolver, ResolutionTrace
from ..utils.units import M2_PER_HA

CARBON_UNIT = "tC"
SOC_REF_UNIT = "tC/ha (0-30 cm)"
IPCC_REFERENCE_DEPTH_CM = 30.0
STOCK_CHANGE_PERIOD_YEARS = 20
#: Tolerância de comparação de ponto flutuante — não é constante científica.
DEPTH_COMPARISON_EPSILON = 1e-9

SOC_MEASURED_EQUATION = (
    "SOC_tC_ha = bulk_density_g_cm3 * depth_cm * organic_carbon_percent "
    "* (1 - coarse_fragment_fraction)"
)
SOC_TIER1_EQUATION = "SOC = SOC_REF * F_LU * F_MG * F_I * area  (IPCC Eq. 2.25)"

#: Usos da terra classificados como Cropland pelo IPCC (Cap.5, Introdução:
#: "Cropland includes ... agroforestry systems where the vegetation structure
#: falls below the thresholds used for the Forest Land category").
CROPLAND_LIKE = {LandUse.CROPLAND, LandUse.AGROFORESTRY, LandUse.SILVOPASTORAL}

FOREST_LIKE = {
    LandUse.NATURAL_FOREST,
    LandUse.SECONDARY_FOREST,
    LandUse.PLANTED_FOREST,
    LandUse.REFORESTATION,
    LandUse.FOREST_RESTORATION,
}

#: Uso da terra -> nível de F_LU da Tabela 5.5.
LAND_USE_TO_FLU_LEVEL = {
    LandUse.CROPLAND: CroplandSystem.LONG_TERM_CULTIVATED,
    LandUse.AGROFORESTRY: CroplandSystem.PERENNIAL_TREE_CROP,
    LandUse.SILVOPASTORAL: CroplandSystem.PERENNIAL_TREE_CROP,
}


class SoilClassificationError(ValueError):
    """Falta região climática ou tipo de solo para o método Tier 1."""


def soil_organic_carbon_density(obs: SoilObservation) -> float:
    """tC/ha a partir da medição de solo."""
    return (
        obs.bulk_density_g_cm3
        * obs.depth_cm
        * obs.organic_carbon_percent
        * (1.0 - obs.coarse_fragment_fraction)
    )


def compute_soil_carbon(
    project: CarbonProject,
    obs: Optional[SoilObservation],
    resolver: FactorResolver,
) -> TracedValue:
    if obs is not None:
        return _measured(project, obs)
    return _tier1(project, resolver)


# ---------------------------------------------------------------------------
# A. medido
# ---------------------------------------------------------------------------

def _measured(project: CarbonProject, obs: SoilObservation) -> TracedValue:
    density_t_ha = soil_organic_carbon_density(obs)
    area_ha = obs.area_ha or project.area_ha
    total = density_t_ha * area_ha
    notes = [
        f"SOC medido até {obs.depth_cm:g} cm. A profundidade faz parte da definição do "
        f"estoque: comparar apenas com inventários da mesma profundidade."
    ]
    if abs(obs.depth_cm - IPCC_REFERENCE_DEPTH_CM) > DEPTH_COMPARISON_EPSILON:
        notes.append(
            f"Profundidade difere dos {IPCC_REFERENCE_DEPTH_CM:g} cm de referência do IPCC: "
            f"não comparável diretamente com SOC_REF da Tabela 2.3."
        )
    return TracedValue(
        value=total,
        unit=CARBON_UNIT,
        estimation_type=obs.estimation_type,
        data_level=DataLevel.MEASURED
        if obs.estimation_type == EstimationType.MEASURED
        else DataLevel.PROJECT_SPECIFIC,
        source=obs.source or "soil_sampling",
        tier=3 if obs.estimation_type == EstimationType.MEASURED else 2,
        uncertainty_percent=obs.uncertainty_percent,
        equations_used=[SOC_MEASURED_EQUATION, "SOC_total = SOC_density * area"],
        inputs={
            "bulk_density_g_cm3": obs.bulk_density_g_cm3,
            "depth_cm": obs.depth_cm,
            "organic_carbon_percent": obs.organic_carbon_percent,
            "coarse_fragment_fraction": obs.coarse_fragment_fraction,
            "area_ha": area_ha,
            "soc_tC_ha": density_t_ha,
            "sample_count": obs.sample_count,
            "m2_per_ha": M2_PER_HA,
        },
        notes=notes,
    )


# ---------------------------------------------------------------------------
# B. Tier 1
# ---------------------------------------------------------------------------

def _factor_uncertainty(resolution: FactorResolution) -> Optional[float]:
    """Incerteza de um fator de mudança de estoque.

    ``uncertainty_percent`` nulo em nível nominal (valor 1,00) significa
    "exato por definição" — a Tabela 5.5 marca esses casos como 'NA' porque a
    incerteza está embutida nos estoques de referência —, não "desconhecido".
    """
    if resolution.uncertainty_percent is not None:
        return resolution.uncertainty_percent
    if resolution.value == 1.0:
        return 0.0
    return None


def _tier1(project: CarbonProject, resolver: FactorResolver) -> TracedValue:
    if project.climate_region is None or project.soil_type is None:
        return TracedValue.not_available(
            CARBON_UNIT,
            "SOC indisponível: sem amostragem de solo e sem climate_region/soil_type para "
            "aplicar o Tier 1 do IPCC. O motor não infere região climática a partir de "
            "coordenadas — o esquema de classificação está no Cap.3 Anexo 3A.5, não transcrito.",
        )

    try:
        soc_ref = resolver.resolve(
            "soil_organic_carbon_reference",
            purpose="SOC_REF (Tier 1)",
            expected_unit=SOC_REF_UNIT,
            climate_region=project.climate_region.value,
            soil_type=project.soil_type.value,
        )
        f_lu, f_mg, f_i = _stock_change_factors(project, resolver)
    except FactorNotFoundError as exc:
        return TracedValue.not_available(CARBON_UNIT, f"SOC indisponível: {exc}")

    density = soc_ref.value * f_lu.value * f_mg.value * f_i.value
    total = density * project.area_ha

    uncertainties = [
        soc_ref.uncertainty_percent,
        _factor_uncertainty(f_lu),
        _factor_uncertainty(f_mg),
        _factor_uncertainty(f_i),
    ]
    combined = (
        sum(u**2 for u in uncertainties) ** 0.5  # type: ignore[operator]
        if all(u is not None for u in uncertainties)
        else None
    )

    notes = [
        "estimated_from_default_factor",
        f"Estoque de EQUILÍBRIO sob o manejo declarado, em {IPCC_REFERENCE_DEPTH_CM:g} cm, "
        f"após o período de referência de {STOCK_CHANGE_PERIOD_YEARS} anos dos fatores. "
        f"NÃO é o estoque atual medido desta área.",
    ]
    if any(r.proxy for r in (soc_ref, f_lu, f_mg, f_i)):
        notes.append("Ao menos um fator do SOC foi resolvido por PROXY.")

    return TracedValue(
        value=total,
        unit=CARBON_UNIT,
        estimation_type=EstimationType.DEFAULT_FACTOR,
        data_level=DataLevel.IPCC_DEFAULT,
        source=soc_ref.source_citation or soc_ref.reference_id,
        tier=1,
        uncertainty_percent=combined,
        factors_used=[soc_ref.factor_id, f_lu.factor_id, f_mg.factor_id, f_i.factor_id],
        equations_used=[SOC_TIER1_EQUATION],
        inputs={
            "soc_ref_tC_ha": soc_ref.value,
            "climate_region": project.climate_region.value,
            "soil_type": project.soil_type.value,
            "F_LU": f_lu.value,
            "F_MG": f_mg.value,
            "F_I": f_i.value,
            "soc_density_tC_ha": density,
            "area_ha": project.area_ha,
            "reference_depth_cm": IPCC_REFERENCE_DEPTH_CM,
        },
        notes=notes,
    )


def _stock_change_factors(
    project: CarbonProject, resolver: FactorResolver
) -> tuple[FactorResolution, FactorResolution, FactorResolution]:
    """Resolve F_LU, F_MG e F_I conforme o uso da terra."""
    if project.land_use in FOREST_LIKE:
        return (
            _forest_unity_factor("FLU", resolver),
            _forest_unity_factor("FMG", resolver),
            _forest_unity_factor("FI", resolver),
        )

    if project.land_use not in CROPLAND_LIKE:
        raise FactorNotFoundError(
            f"SOC Tier 1 não implementado para land_use '{project.land_use.value}'. "
            f"Implementados: Forest Land (Cap.4) e Cropland/agrofloresta (Cap.5). "
            f"Grassland exige o Cap.6, ainda não transcrito."
        )

    temperature_regime, moisture_regime = CLIMATE_REGION_TO_REGIME[
        project.climate_region.value  # type: ignore[union-attr]
    ]
    level = LAND_USE_TO_FLU_LEVEL[project.land_use]

    f_lu = _resolve_stock_factor(
        resolver, "FLU", level.value, temperature_regime, moisture_regime, "F_LU (uso da terra)"
    )

    # Cultivos perenes/arbóreos são classe terminal na Figura 5.1: a subdivisão
    # por preparo do solo e nível de insumo aplica-se ao cultivo anual.
    if level == CroplandSystem.PERENNIAL_TREE_CROP:
        purpose = "nominal (cultivo perene é classe terminal na Figura 5.1)"
        f_mg = _resolve_stock_factor(
            resolver, "FMG", TillageManagement.FULL.value, temperature_regime, moisture_regime,
            f"F_MG {purpose}",
        )
        f_i = _resolve_stock_factor(
            resolver, "FI", CarbonInputLevel.MEDIUM.value, temperature_regime, moisture_regime,
            f"F_I {purpose}",
        )
        return f_lu, f_mg, f_i

    tillage = (project.tillage or TillageManagement.FULL).value
    input_level = (project.carbon_input_level or CarbonInputLevel.MEDIUM).value
    f_mg = _resolve_stock_factor(
        resolver, "FMG", tillage, temperature_regime, moisture_regime, "F_MG (preparo do solo)"
    )
    f_i = _resolve_stock_factor(
        resolver, "FI", input_level, temperature_regime, moisture_regime, "F_I (nível de insumo)"
    )
    return f_lu, f_mg, f_i


def _resolve_stock_factor(
    resolver: FactorResolver,
    kind: str,
    level: str,
    temperature_regime: Optional[str],
    moisture_regime: Optional[str],
    purpose: str,
) -> FactorResolution:
    """Tenta o regime exato e depois os agrupamentos declarados na Tabela 5.5."""
    attempts: list[tuple[Optional[str], Optional[str]]] = [(temperature_regime, moisture_regime)]
    if temperature_regime in ("temperate_boreal", "tropical"):
        attempts.append(("temperate_boreal_and_tropical", moisture_regime))
    attempts.append(("all", "dry_and_moist_wet"))

    last_error: Optional[Exception] = None
    for temp, moist in attempts:
        try:
            return resolver.resolve(
                "soil_stock_change_factor",
                purpose=purpose,
                expected_unit="dimensionless",
                factor_kind=kind,
                level=level,
                temperature_regime=temp,
                moisture_regime=moist,
            )
        except FactorNotFoundError as exc:
            last_error = exc
    raise FactorNotFoundError(
        f"{purpose}: nenhum fator da Tabela 5.5 para nível '{level}' e regime "
        f"'{temperature_regime}/{moisture_regime}'. ({last_error})"
    )


def _forest_unity_factor(kind: str, resolver: FactorResolver) -> FactorResolution:
    """Forest Land, Tier 1: todos os fatores de mudança de estoque valem 1.

    IPCC 2006 Vol.4 Cap.4, Seção 4.2.3.2: "If using Approach 1 activity data,
    stock change factors, including input, management and disturbance regime,
    are equal to 1 using the Tier 1 approach. Consequently, only reference C
    stocks are needed to apply the method."
    """
    citation = None
    if "IPCC2006_V4_CH4" in resolver.registry.references:
        citation = resolver.registry.references.get("IPCC2006_V4_CH4").citation()
    resolution = FactorResolution(
        factor_id=f"{kind}_FOREST_LAND_TIER1_UNITY",
        category="soil_stock_change_factor",
        value=1.0,
        unit="dimensionless",
        data_level=DataLevel.IPCC_DEFAULT,
        tier=1,
        reference_id="IPCC2006_V4_CH4",
        page_or_table="Seção 4.2.3.2, 'Mineral soils / Tier 1'",
        source_citation=citation,
        methodology="IPCC 2006 Tier 1 (Forest Land)",
        validation_status=ValidationStatus.VALIDATED,
        uncertainty_percent=0.0,
        trace=ResolutionTrace(
            requested={"factor_kind": kind, "land_use": "forest"},
            selected_factor=f"{kind}_FOREST_LAND_TIER1_UNITY",
            selection_reason=(
                "Regra metodológica do Cap.4: em Forest Land no Tier 1 todos os fatores de "
                "mudança de estoque do solo valem 1, restando apenas o estoque de referência."
            ),
            data_level=DataLevel.IPCC_DEFAULT,
            resolved=True,
        ),
    )
    return resolver.register_direct(resolution)
