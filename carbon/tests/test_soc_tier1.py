"""Normalização de solos brasileiros

Referências das fontes primárias citadas em cada teste.
"""

from __future__ import annotations

import pytest

from carbon.core import soil_engine
from carbon.core.carbon_engine import CarbonEngine, CarbonEngineConfig
from carbon.core.gwp import GWPMixingError, GWPNotAvailableError, assert_single_gwp_version, to_co2e
from carbon.core.n2o_engine import N2O_N_TO_N2O_RATIO, direct_n2o_from_nitrogen
from carbon.factors.registry import FactorNotFoundError, FactorRegistry
from carbon.factors.soil_classification import (
    SoilCorrespondenceError,
    to_ipcc_soil_type,
)
from carbon.models.enums import (
    CalculationMode,
    CarbonInputLevel,
    DataLevel,
    EstimationType,
    IPCCClimateRegion,
    IPCCSoilType,
    LandUse,
    ResultStatus,
    TillageManagement,
    ValidationStatus,
)
from carbon.models.inventory import (
    BelowgroundObservation,
    BiomassObservation,
    CarbonInventory,
    SoilObservation,
)
from carbon.models.project import CarbonProject, Coordinates
from carbon.services.factor_service import (
    FactorResolver,
    ProjectParameter,
    ProxyAuthorization,
    ProxyNotAuthorizedError,
)

from .conftest import empty_inventory, saf_project


# --- Normalização de solos brasileiros ---------------------------


def test_sibcs_latossolo_maps_to_lac_but_flags_unvalidated_step():
    resolution = to_ipcc_soil_type("Latossolo")
    assert resolution.ipcc_soil_type == IPCCSoilType.LAC
    assert resolution.wrb_equivalent == "Ferralsols"
    assert resolution.correspondence_status == ValidationStatus.REQUIRES_VALIDATION
    assert resolution.warnings


def test_wrb_to_ipcc_step_is_validated_from_table_23_footnotes():
    resolution = to_ipcc_soil_type("Ferralsols", classification="WRB")
    assert resolution.ipcc_soil_type == IPCCSoilType.LAC
    assert resolution.correspondence_status == ValidationStatus.VALIDATED
    assert "Tabela 2.3" in (resolution.correspondence_source or "")


def test_ambiguous_sibcs_order_is_refused_not_approximated():
    """Neossolo agrupa solos que caem em classes IPCC diferentes."""
    with pytest.raises(SoilCorrespondenceError) as exc:
        to_ipcc_soil_type("Neossolo")
    assert "SUBGRUPO" in str(exc.value)


def test_organossolo_is_routed_away_from_mineral_soil_method():
    with pytest.raises(SoilCorrespondenceError) as exc:
        to_ipcc_soil_type("Organossolo")
    assert "orgânico" in str(exc.value).lower()


def test_soil_class_outside_ipcc_footnotes_is_refused():
    with pytest.raises(SoilCorrespondenceError):
        to_ipcc_soil_type("Plintossolo")
    with pytest.raises(SoilCorrespondenceError):
        to_ipcc_soil_type("Planosols", classification="WRB")


# --- Tier 1 do IPCC: SOC = SOC_REF x F_LU x F_MG x F_I x área -------------

def test_soc_tier1_agroforestry_uses_perennial_tree_crop_factor(registry):
    """IPCC Vol.4 Cap.5: agrofloresta é Cropland; F_LU de perene/arbóreo = 1,00.

    SOC = 47 (tropical moist, LAC) x 1,00 x 1,00 x 1,00 x 100 ha = 4700 tC.
    """
    project = saf_project()
    resolver = FactorResolver(registry)
    result = soil_engine.compute_soil_carbon(project, None, resolver)

    assert result.value == pytest.approx(4700.0)
    assert result.estimation_type == EstimationType.DEFAULT_FACTOR
    assert result.inputs["F_LU"] == 1.00
    assert result.inputs["soc_ref_tC_ha"] == 47.0
    assert result.inputs["reference_depth_cm"] == 30.0
    assert "FLU_PERENNIAL_TREE_CROP_ALL_DRY_AND_MOIST_WET" in result.factors_used
    assert any("EQUILÍBRIO" in n for n in result.notes)


def test_soc_tier1_annual_cropland_applies_tillage_and_input(registry):
    """Cropland anual em trópico úmido, plantio direto e insumo alto com esterco.

    SOC = 47 x 0,48 x 1,22 x 1,44 x 100 ha (Tabelas 2.3 e 5.5).
    """
    project = saf_project(
        land_use=LandUse.CROPLAND,
        tillage=TillageManagement.NO_TILL,
        carbon_input_level=CarbonInputLevel.HIGH_WITH_MANURE,
    )
    result = soil_engine.compute_soil_carbon(project, None, FactorResolver(registry))

    assert result.value == pytest.approx(47.0 * 0.48 * 1.22 * 1.44 * 100.0)
    assert result.inputs["F_LU"] == 0.48
    assert result.inputs["F_MG"] == 1.22
    assert result.inputs["F_I"] == 1.44


def test_soc_tier1_forest_uses_unity_stock_change_factors(registry):
    """IPCC Vol.4 Cap.4, Seção 4.2.3.2: em Forest Land no Tier 1 os fatores de
    mudança de estoque valem 1 e resta apenas o estoque de referência."""
    project = saf_project(land_use=LandUse.NATURAL_FOREST)
    result = soil_engine.compute_soil_carbon(project, None, FactorResolver(registry))

    assert result.value == pytest.approx(47.0 * 100.0)
    assert result.inputs["F_LU"] == 1.0
    assert result.inputs["F_MG"] == 1.0
    assert result.inputs["F_I"] == 1.0
    assert "FLU_FOREST_LAND_TIER1_UNITY" in result.factors_used


def test_soc_tier1_uncertainty_combines_only_declared_components(registry):
    """SOC_REF ±90% (nota da Tabela 2.3) e F_LU ±50% (Tabela 5.5); F_MG e F_I
    nominais são exatos por definição, não desconhecidos."""
    result = soil_engine.compute_soil_carbon(saf_project(), None, FactorResolver(registry))
    assert result.uncertainty_percent == pytest.approx((90.0**2 + 50.0**2) ** 0.5)


def test_soc_tier1_refuses_pasture_without_transcribed_chapter(registry):
    """Grassland exige o Cap.6, não transcrito: o motor recusa em vez de
    aproximar com fatores de cropland."""
    project = saf_project(land_use=LandUse.PASTURE)
    result = soil_engine.compute_soil_carbon(project, None, FactorResolver(registry))
    assert result.value is None
    assert "Cap.6" in result.notes[0]


def test_soc_measured_and_tier1_are_never_mixed(registry):
    """Medição e Tier 1 produzem proveniências distintas e não se combinam."""
    project = saf_project()
    obs = SoilObservation(depth_cm=30.0, bulk_density_g_cm3=1.2, organic_carbon_percent=2.4)

    measured = soil_engine.compute_soil_carbon(project, obs, FactorResolver(registry))
    tier1 = soil_engine.compute_soil_carbon(project, None, FactorResolver(registry))

    assert measured.estimation_type == EstimationType.MEASURED
    assert measured.data_level == DataLevel.MEASURED
    assert measured.factors_used == []
    assert tier1.estimation_type == EstimationType.DEFAULT_FACTOR
    assert tier1.factors_used
    assert measured.value != tier1.value


def test_soc_measured_flags_non_reference_depth(registry):
    """Profundidade fora dos 30 cm de referência quebra a comparabilidade."""
    obs = SoilObservation(depth_cm=100.0, bulk_density_g_cm3=1.2, organic_carbon_percent=2.0)
    result = soil_engine.compute_soil_carbon(saf_project(), obs, FactorResolver(registry))
    assert any("30 cm de referência" in n for n in result.notes)
