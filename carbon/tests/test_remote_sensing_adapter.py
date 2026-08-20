"""Adapter sensoriamento remoto -> inventário -> Carbon Engine.

Verifica a fronteira: o motor recebe MATÉRIA SECA e aplica a fração de
carbono uma única vez; a hierarquia de fontes nunca deixa um dado fraco
substituir um forte em silêncio; e o motor continua funcionando sem GEE.
"""

from __future__ import annotations

import pytest

from carbon.core.carbon_engine import CarbonEngine
from carbon.models.enums import CalculationMode, EstimationType, LandUse
from carbon.models.remote_sensing import (
    BiomassRemoteObservation,
    BiomassSourceLevel,
    LandCoverConsistency,
    SamplingSupport,
)
from carbon.services.gee_provider import GoogleEarthEngineCarbonProvider, observe_all
from carbon.services.geometry_service import aoi_from_point
from carbon.services.remote_sensing_adapter import (
    RemoteSensingInventoryAdapter,
    select_biomass_source,
)
from carbon.tests.conftest import empty_inventory, saf_project
from carbon.tests.gee_stubs import StubEarthEngineClient, gedi_payload

RIBEIRA_LAT = -24.497
RIBEIRA_LON = -47.844


@pytest.fixture
def aoi():
    return aoi_from_point(RIBEIRA_LAT, RIBEIRA_LON, 100.0)


def usable_observation(**overrides) -> BiomassRemoteObservation:
    base = dict(
        available=True,
        support=SamplingSupport.USABLE,
        sample_count=40,
        mean_agbd_mg_ha=120.0,
        std_agbd_mg_ha=30.0,
        agb_density_t_ha=120.0,
        agb_total_t=12_000.0,
        sampling_uncertainty_percent=7.75,
        uncertainty_available=True,
    )
    base.update(overrides)
    return BiomassRemoteObservation(**base)


# --- hierarquia de fontes ---------------------------------------------------

def test_field_measurement_beats_remote_sensing():
    decision = select_biomass_source(
        biomass=usable_observation(), field_measurement_available=True
    )
    assert decision.selected is BiomassSourceLevel.FIELD_MEASUREMENT
    assert any(
        r["level"] == BiomassSourceLevel.GEDI_VALID_OBSERVATIONS.value
        for r in decision.rejected
    )


def test_calibrated_project_model_beats_global_product():
    decision = select_biomass_source(
        biomass=usable_observation(), calibrated_model_available=True
    )
    assert decision.selected is BiomassSourceLevel.PROJECT_CALIBRATED_MODEL


def test_usable_gedi_is_selected():
    decision = select_biomass_source(biomass=usable_observation())
    assert decision.selected is BiomassSourceLevel.GEDI_VALID_OBSERVATIONS
    assert "40 footprints" in decision.reason


def test_insufficient_sampling_falls_back_to_the_engine():
    decision = select_biomass_source(
        biomass=usable_observation(support=SamplingSupport.LOW_SUPPORT, sample_count=6)
    )
    assert decision.selected is BiomassSourceLevel.IPCC_REGIONAL_DEFAULT
    assert decision.delegated_to_engine is True
    assert any("insufficient GEDI sampling" in r["reason"] for r in decision.rejected)


def test_blocking_land_cover_inconsistency_refuses_remote_biomass():
    decision = select_biomass_source(
        biomass=usable_observation(),
        consistency=LandCoverConsistency(
            checked=True, consistent=False, blocking=True, severity="error",
            message="95% da AOI é água",
        ),
    )
    assert decision.selected is BiomassSourceLevel.UNAVAILABLE
    assert "água" in decision.rejected[0]["reason"]


def test_every_rejected_level_carries_a_reason():
    decision = select_biomass_source(biomass=None)
    assert decision.rejected
    for entry in decision.rejected:
        assert entry["reason"]


# --- adapter ----------------------------------------------------------------

def test_adapter_produces_dry_matter_observation(aoi):
    adapter = RemoteSensingInventoryAdapter()
    observation, warnings = adapter.build_aboveground_observation(usable_observation())
    assert observation.dry_biomass_t_ha == 120.0
    assert observation.carbon_t is None  # nunca carbono
    assert observation.estimation_type is EstimationType.REMOTE_SENSING
    assert "GEDI04_A" in observation.source
    assert observation.uncertainty_percent == pytest.approx(7.75)


def test_adapter_refuses_to_truncate_uncertainty_above_100_percent():
    adapter = RemoteSensingInventoryAdapter()
    observation, warnings = adapter.build_aboveground_observation(
        usable_observation(sampling_uncertainty_percent=180.0)
    )
    # Não vira 100: deixa de ser propagada e o motivo aparece.
    assert observation.uncertainty_percent is None
    assert any("NÃO foi truncada" in w for w in warnings)


def test_adapter_returns_nothing_when_biomass_is_unavailable():
    adapter = RemoteSensingInventoryAdapter()
    observation, warnings = adapter.build_aboveground_observation(
        BiomassRemoteObservation(reason="sem footprints")
    )
    assert observation is None
    assert warnings == ["sem footprints"]


def test_inventory_leaves_unobserved_pools_absent(aoi):
    provider = GoogleEarthEngineCarbonProvider(StubEarthEngineClient())
    bundle = observe_all(
        provider,
        aoi,
        declared_land_use=LandUse.AGROFORESTRY.value,
        current_year=2024,
    )
    inventory, _ = RemoteSensingInventoryAdapter().to_inventory(
        bundle, project_id="p", inventory_id="inv", year=2024
    )
    assert inventory.aboveground is not None
    assert inventory.belowground is None
    assert inventory.deadwood is None
    assert inventory.litter is None
    assert inventory.soil is None
    assert inventory.mode is CalculationMode.INVENTORY


def test_inventory_without_biomass_does_not_fabricate_a_pool(aoi):
    provider = GoogleEarthEngineCarbonProvider(
        StubEarthEngineClient(gedi=gedi_payload(sample_count=0, mean=None))
    )
    bundle = observe_all(
        provider,
        aoi,
        declared_land_use=LandUse.AGROFORESTRY.value,
        current_year=2024,
    )
    inventory, warnings = RemoteSensingInventoryAdapter().to_inventory(
        bundle, project_id="p", inventory_id="inv", year=2024
    )
    assert inventory.aboveground is None
    assert warnings


# --- integração com o motor -------------------------------------------------

def test_engine_applies_carbon_fraction_exactly_once(aoi):
    """12 000 t de matéria seca -> carbono = 12 000 x fração, uma vez só."""
    provider = GoogleEarthEngineCarbonProvider(StubEarthEngineClient())
    bundle = observe_all(
        provider,
        aoi,
        declared_land_use=LandUse.AGROFORESTRY.value,
        current_year=2024,
    )
    inventory, _ = RemoteSensingInventoryAdapter().to_inventory(
        bundle, project_id="saf-br", inventory_id="inv-gee", year=2024
    )
    project = saf_project(area_ha=100.0)
    result = CarbonEngine().calculate(project, inventory)

    agb = result.carbon_stock.pools["aboveground_biomass"]
    assert agb.dry_biomass_t.value == pytest.approx(12_000.0)
    fraction = agb.carbon_t.inputs["carbon_fraction"]
    assert agb.carbon_t.value == pytest.approx(12_000.0 * fraction)
    # A fração aplicada é um fator do registro, com id rastreável.
    assert agb.carbon_t.inputs["carbon_fraction_factor_id"]
    assert agb.carbon_t.estimation_type is EstimationType.REMOTE_SENSING


def test_engine_still_runs_without_any_gee_input():
    """Regra de ouro: o núcleo científico não depende do Earth Engine."""
    result = CarbonEngine().calculate(saf_project(), empty_inventory())
    assert result.carbon_stock is not None
    assert result.audit is not None


def test_missing_remote_data_never_becomes_zero_in_the_result(aoi):
    provider = GoogleEarthEngineCarbonProvider(
        StubEarthEngineClient(gedi=gedi_payload(sample_count=0, mean=None))
    )
    bundle = observe_all(
        provider,
        aoi,
        declared_land_use=LandUse.AGROFORESTRY.value,
        current_year=2024,
    )
    inventory, _ = RemoteSensingInventoryAdapter().to_inventory(
        bundle, project_id="saf-br", inventory_id="inv-empty", year=2024
    )
    result = CarbonEngine().calculate(saf_project(), inventory)
    total = result.carbon_stock.total_carbon_t
    assert total is None or total > 0
    assert "aboveground_biomass" not in [
        name
        for name, pool in result.carbon_stock.pools.items()
        if pool.carbon_t.value == 0
    ]
