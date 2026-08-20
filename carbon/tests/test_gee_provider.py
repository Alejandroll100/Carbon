"""Provider Google Earth Engine — comportamento científico, sem rede.

Nenhum teste aqui toca o Earth Engine real: o cliente é um stub. O que se
verifica é a MATEMÁTICA e as REGRAS, não HTTP 200.
"""

from __future__ import annotations

import math
import sys
import types

import pytest

from carbon.config.gee import (
    AUTHENTICATION_HINT,
    EarthEngineAuthenticationError,
    EarthEngineDisabledError,
    GEEConfig,
    initialize_earth_engine,
)
from carbon.models.enums import EstimationType, LandUse
from carbon.models.remote_sensing import CoverageStatus, SamplingSupport
from carbon.services.gee_cache import GEEQueryCache
from carbon.services.gee_datasets import GEDI_L4A, gedi_covers_latitude, gedi_covers_year
from carbon.services.gee_provider import (
    MIN_FOOTPRINTS_FOR_SAMPLING_UNCERTAINTY,
    USABLE_SUPPORT_MIN_FOOTPRINTS,
    GoogleEarthEngineCarbonProvider,
    biomass_periods_comparable,
    check_land_cover_consistency,
    classify_sampling_support,
    mg_ha_to_t_ha,
    observation_window,
    observe_all,
    sampling_uncertainty_percent,
    total_dry_biomass_t,
)
from carbon.services.geometry_service import aoi_from_point
from carbon.services.geospatial_service import NullRemoteSensingProvider
from carbon.services.inventory_service import Z_SCORE_95
from carbon.tests.gee_stubs import (
    StubEarthEngineClient,
    gedi_payload,
    land_cover_payload,
    sentinel_payload,
)

RIBEIRA_LAT = -24.497
RIBEIRA_LON = -47.844


@pytest.fixture
def aoi():
    return aoi_from_point(RIBEIRA_LAT, RIBEIRA_LON, 100.0)


def make_provider(client: StubEarthEngineClient, **kwargs):
    return GoogleEarthEngineCarbonProvider(client, **kwargs)


# --- unidades ---------------------------------------------------------------

def test_mg_per_ha_is_tonne_per_ha_and_scales_by_area():
    """AGBD 120 Mg/ha em 100 ha = 12 000 t de biomassa seca. Sem fração de carbono."""
    density = mg_ha_to_t_ha(120.0)
    assert density == 120.0
    assert total_dry_biomass_t(density, 100.0) == pytest.approx(12_000.0)


def test_carbon_fraction_is_not_applied_by_the_provider(aoi):
    """O total entregue é MATÉRIA SECA: 120 x 100 = 12 000, não 12 000 x 0,47."""
    provider = make_provider(StubEarthEngineClient(gedi=gedi_payload(mean=120.0)))
    observation = provider.observe_biomass(aoi, 2024)
    assert observation.agb_total_t == pytest.approx(12_000.0)


# --- suporte amostral -------------------------------------------------------

def test_sampling_support_thresholds():
    assert classify_sampling_support(0) is SamplingSupport.UNAVAILABLE
    assert classify_sampling_support(1) is SamplingSupport.VERY_LOW_SUPPORT
    assert classify_sampling_support(4) is SamplingSupport.VERY_LOW_SUPPORT
    assert classify_sampling_support(5) is SamplingSupport.LOW_SUPPORT
    assert classify_sampling_support(19) is SamplingSupport.LOW_SUPPORT
    assert classify_sampling_support(USABLE_SUPPORT_MIN_FOOTPRINTS) is SamplingSupport.USABLE


def test_gedi_without_footprints_is_unavailable_not_zero(aoi):
    provider = make_provider(StubEarthEngineClient(gedi=gedi_payload(sample_count=0, mean=None)))
    observation = provider.observe_biomass(aoi, 2024)
    assert observation.available is False
    assert observation.agb_total_t is None
    assert observation.coverage_status is CoverageStatus.NO_OBSERVATIONS
    assert "insufficient GEDI sampling" in observation.reason
    # Regra central: ausência jamais vira zero.
    assert observation.mean_agbd_mg_ha is None


def test_gedi_with_footprints_produces_biomass_and_statistics(aoi):
    provider = make_provider(StubEarthEngineClient(gedi=gedi_payload(sample_count=40)))
    observation = provider.observe_biomass(aoi, 2024)
    assert observation.available is True
    assert observation.support is SamplingSupport.USABLE
    assert observation.sample_count == 40
    assert observation.median_agbd_mg_ha == 118.0
    assert observation.min_agbd_mg_ha == 60.0
    assert observation.max_agbd_mg_ha == 210.0


def test_sample_count_and_sampled_fraction_are_propagated(aoi):
    provider = make_provider(StubEarthEngineClient(gedi=gedi_payload(sample_count=40)))
    observation = provider.observe_biomass(aoi, 2024)
    footprint_area_ha = math.pi * (25.0 / 2.0) ** 2 / 10_000.0
    assert observation.sampled_area_ha == pytest.approx(40 * footprint_area_ha)
    assert observation.sampled_fraction_of_aoi == pytest.approx(
        40 * footprint_area_ha / 100.0
    )
    assert observation.provenance.sample_count == 40


def test_single_footprint_is_flagged_and_gets_no_uncertainty(aoi):
    provider = make_provider(StubEarthEngineClient(gedi=gedi_payload(sample_count=1, std=None)))
    observation = provider.observe_biomass(aoi, 2024)
    assert observation.support is SamplingSupport.VERY_LOW_SUPPORT
    assert observation.uncertainty_available is False
    assert observation.sampling_uncertainty_percent is None
    assert any("very_low_support" in w for w in observation.warnings)


# --- incerteza --------------------------------------------------------------

def test_sampling_uncertainty_is_the_standard_error_of_the_mean():
    """1.96 x (s/sqrt(n)) / media x 100 — mesma convenção do inventário de parcelas."""
    expected = Z_SCORE_95 * (30.0 / math.sqrt(40)) / 120.0 * 100
    assert sampling_uncertainty_percent(120.0, 30.0, 40) == pytest.approx(expected)


def test_uncertainty_is_never_fabricated():
    assert sampling_uncertainty_percent(120.0, None, 40) is None
    assert sampling_uncertainty_percent(None, 30.0, 40) is None
    assert (
        sampling_uncertainty_percent(120.0, 30.0, MIN_FOOTPRINTS_FOR_SAMPLING_UNCERTAINTY - 1)
        is None
    )
    assert sampling_uncertainty_percent(0.0, 30.0, 40) is None


def test_prediction_error_is_preserved_raw_and_declared_as_not_combined(aoi):
    provider = make_provider(StubEarthEngineClient(gedi=gedi_payload(prediction_se=22.5)))
    observation = provider.observe_biomass(aoi, 2024)
    assert observation.mean_prediction_se_mg_ha == 22.5
    assert observation.model_error_included is False
    assert any("agbd_se" in w for w in observation.warnings)
    # A incerteza propagada é SÓ a amostral, e o método diz isso.
    assert "amostragem" in observation.uncertainty_method
    assert observation.uncertainty_source == "GEDI"


# --- cobertura espacial e temporal -----------------------------------------

def test_gedi_latitude_coverage_is_respected():
    assert gedi_covers_latitude(RIBEIRA_LAT) is True
    assert gedi_covers_latitude(60.0) is False
    assert gedi_covers_latitude(-70.0) is False


def test_aoi_outside_gedi_latitude_returns_unavailable():
    high_latitude = aoi_from_point(64.5, 25.0, 100.0)
    provider = make_provider(StubEarthEngineClient())
    observation = provider.observe_biomass(high_latitude, 2024)
    assert observation.available is False
    assert observation.coverage_status is CoverageStatus.OUTSIDE_SPATIAL_COVERAGE
    assert "51.6" in observation.reason


def test_baseline_year_outside_gedi_period_is_refused(aoi):
    assert gedi_covers_year(2010) is False
    provider = make_provider(StubEarthEngineClient())
    observation = provider.observe_biomass(aoi, 2010)
    assert observation.available is False
    assert observation.coverage_status is CoverageStatus.OUTSIDE_TEMPORAL_COVERAGE
    assert "GEDI unavailable for requested period" in observation.reason
    # E o cliente nem chegou a ser consultado.
    assert provider.client.call_count("gedi") == 0


def test_observation_window_defaults_to_the_calendar_year():
    assert observation_window(2024) == ("2024-01-01", "2025-01-01")
    assert observation_window(2024, expansion_months=6) == ("2023-07-01", "2025-07-01")


def test_actual_observation_window_is_reported(aoi):
    provider = make_provider(StubEarthEngineClient())
    observation = provider.observe_biomass(aoi, 2024)
    assert observation.window.requested_year == 2024
    assert observation.window.requested_start == "2024-01-01"
    assert observation.window.actual_observation_start == "2024-02-01"
    assert observation.window.actual_observation_end == "2024-11-01"
    assert observation.window.scene_count == 9


# --- falhas de consulta -----------------------------------------------------

def test_query_failure_never_becomes_zero(aoi):
    provider = make_provider(StubEarthEngineClient(fail={"gedi"}))
    observation = provider.observe_biomass(aoi, 2024)
    assert observation.available is False
    assert observation.coverage_status is CoverageStatus.QUERY_FAILED
    assert observation.agb_total_t is None
    assert "não zero" in observation.reason


# --- cobertura da terra -----------------------------------------------------

def test_land_cover_distribution_and_dominance(aoi):
    provider = make_provider(StubEarthEngineClient())
    observation = provider.observe_land_cover(aoi, 2024)
    assert observation.available is True
    assert observation.dominant_land_cover == "trees"
    assert observation.land_cover_distribution_percent["trees"] == pytest.approx(70.0)
    assert observation.land_cover_distribution_percent["crops"] == pytest.approx(20.0)
    assert sum(observation.land_cover_distribution_percent.values()) == pytest.approx(100.0)
    assert observation.tree_probability_mean == 0.74


def test_land_cover_without_scenes_is_unavailable(aoi):
    provider = make_provider(
        StubEarthEngineClient(land_cover=land_cover_payload(counts={}))
    )
    observation = provider.observe_land_cover(aoi, 2024)
    assert observation.available is False
    assert observation.dominant_land_cover is None


def test_water_dominated_aoi_blocks_forest_declaration(aoi):
    provider = make_provider(
        StubEarthEngineClient(
            land_cover=land_cover_payload(counts={"water": 9500.0, "trees": 500.0})
        )
    )
    land_cover = provider.observe_land_cover(aoi, 2024)
    consistency = check_land_cover_consistency(LandUse.NATURAL_FOREST.value, land_cover)
    assert consistency.consistent is False
    assert consistency.blocking is True
    assert consistency.severity == "error"
    assert "95.0%" in consistency.message


def test_atypical_but_not_blocking_cover_only_warns(aoi):
    provider = make_provider(
        StubEarthEngineClient(
            land_cover=land_cover_payload(counts={"crops": 9000.0, "trees": 1000.0})
        )
    )
    land_cover = provider.observe_land_cover(aoi, 2024)
    consistency = check_land_cover_consistency(LandUse.NATURAL_FOREST.value, land_cover)
    assert consistency.consistent is False
    assert consistency.blocking is False
    assert consistency.severity == "warning"


def test_consistent_cover_is_reported_as_such(aoi):
    provider = make_provider(StubEarthEngineClient())
    land_cover = provider.observe_land_cover(aoi, 2024)
    consistency = check_land_cover_consistency(LandUse.AGROFORESTRY.value, land_cover)
    assert consistency.consistent is True
    assert consistency.blocking is False


# --- Sentinel-2 e índices ---------------------------------------------------

def test_sentinel_without_scenes_is_unavailable(aoi):
    provider = make_provider(
        StubEarthEngineClient(sentinel=sentinel_payload(scene_count=0, ndvi=None))
    )
    indices = provider.observe_vegetation_indices(aoi, 2024)
    assert indices.available is False
    assert indices.coverage_status is CoverageStatus.NO_OBSERVATIONS
    assert indices.ndvi is None


def test_cloud_masked_fraction_is_derived_from_valid_fraction(aoi):
    provider = make_provider(
        StubEarthEngineClient(sentinel=sentinel_payload(valid_fraction=0.6))
    )
    indices = provider.observe_vegetation_indices(aoi, 2024)
    assert indices.cloud_masked_fraction == pytest.approx(0.4)


def test_spectral_indices_carry_no_carbon_field(aoi):
    """O modelo de índices não tem, por construção, nenhum campo em carbono."""
    provider = make_provider(StubEarthEngineClient())
    indices = provider.observe_vegetation_indices(aoi, 2024)
    assert indices.ndvi == 0.78
    assert indices.carbon_equivalent is None
    assert "direct_carbon_conversion" in indices.forbidden_uses
    payload = indices.model_dump()
    for field in payload:
        assert "carbon" not in field or field == "carbon_equivalent"
        assert "biomass" not in field
        assert not field.endswith("_tc")


def test_estimate_change_never_derives_carbon_from_spectra(aoi):
    provider = make_provider(StubEarthEngineClient())
    traced = provider.estimate_change(
        geometry=aoi.geojson, baseline_year=2020, current_year=2024
    )
    assert traced.value is None
    assert traced.estimation_type is EstimationType.NOT_AVAILABLE


def test_observed_change_separates_spectral_from_carbon(aoi):
    client = StubEarthEngineClient(
        gedi_by_year={
            2020: gedi_payload(sample_count=0, mean=None),
            2024: gedi_payload(sample_count=40),
        }
    )
    provider = make_provider(client)
    bundle = observe_all(
        provider,
        aoi,
        declared_land_use=LandUse.AGROFORESTRY.value,
        current_year=2024,
        baseline_year=2020,
    )
    change = bundle.change
    assert change.available is True
    assert change.delta_ndvi == pytest.approx(0.0)
    assert change.carbon_change_available is False
    assert "not_available" in change.carbon_change_reason
    assert "não vira" in " ".join(change.warnings)


def test_carbon_change_requires_usable_support_in_both_periods():
    strong = gedi_payload(sample_count=40)
    weak = gedi_payload(sample_count=3)
    from carbon.models.remote_sensing import BiomassRemoteObservation

    usable = BiomassRemoteObservation(
        available=True, support=SamplingSupport.USABLE, sample_count=40
    )
    low = BiomassRemoteObservation(
        available=True, support=SamplingSupport.VERY_LOW_SUPPORT, sample_count=3
    )
    assert biomass_periods_comparable(usable, usable)[0] is True
    assert biomass_periods_comparable(low, usable)[0] is False
    assert biomass_periods_comparable(None, usable)[0] is False
    assert strong["sample_count"] > weak["sample_count"]


# --- proveniência -----------------------------------------------------------

def test_provenance_is_complete(aoi):
    provider = make_provider(StubEarthEngineClient())
    observation = provider.observe_biomass(aoi, 2024)
    provenance = observation.provenance
    assert provenance.provider == "google_earth_engine"
    assert provenance.dataset_id == GEDI_L4A.dataset_id
    assert provenance.dataset_name == GEDI_L4A.name
    assert provenance.bands == ["agbd", "agbd_se"]
    assert provenance.units.startswith("Mg/ha")
    assert provenance.spatial_resolution_m == 25.0
    assert provenance.geometry_hash == aoi.geometry_hash
    assert provenance.geometry_source == aoi.geometry_source.value
    assert provenance.area_ha == 100.0
    assert provenance.scale_m == 25.0
    assert provenance.reducer
    assert provenance.requested_year == 2024
    assert provenance.retrieval_timestamp
    assert provenance.quality_filters
    assert provenance.reference_id == "GEE_GEDI_L4A_RASTER"
    assert provenance.source_url.startswith("https://")
    assert provenance.estimation_type is EstimationType.REMOTE_SENSING
    assert provenance.limitations


def test_traced_value_from_biomass_is_dry_matter(aoi):
    provider = make_provider(StubEarthEngineClient())
    traced = provider.estimate_biomass(geometry=aoi.geojson, year=2024)
    assert traced.unit == "t dry matter"
    assert traced.estimation_type is EstimationType.REMOTE_SENSING
    assert "AGB_total = AGBD_density * area" in traced.equations_used
    assert any("fração de carbono" in note for note in traced.notes)


# --- cache ------------------------------------------------------------------

def test_cache_avoids_redundant_calls_and_records_acquisition(aoi):
    client = StubEarthEngineClient()
    provider = make_provider(client, cache=GEEQueryCache(ttl_seconds=60))
    first = provider.observe_biomass(aoi, 2024)
    second = provider.observe_biomass(aoi, 2024)
    assert client.call_count("gedi") == 1
    assert first.provenance.cache_hit is False
    assert second.provenance.cache_hit is True
    assert second.provenance.retrieval_timestamp == first.provenance.retrieval_timestamp


def test_cache_disabled_by_default(aoi):
    client = StubEarthEngineClient()
    provider = make_provider(client)
    provider.observe_biomass(aoi, 2024)
    provider.observe_biomass(aoi, 2024)
    assert client.call_count("gedi") == 2


# --- autenticação -----------------------------------------------------------

def test_disabled_configuration_raises_explicit_error():
    with pytest.raises(EarthEngineDisabledError):
        initialize_earth_engine(GEEConfig(enabled=False))


def test_unauthenticated_session_raises_actionable_error(monkeypatch):
    fake = types.ModuleType("ee")

    def initialize(*args, **kwargs):
        raise RuntimeError("Please authorize access to your Earth Engine account")

    fake.Initialize = initialize
    fake.ServiceAccountCredentials = lambda *a, **k: object()
    monkeypatch.setitem(sys.modules, "ee", fake)
    with pytest.raises(EarthEngineAuthenticationError) as excinfo:
        initialize_earth_engine(GEEConfig(enabled=True))
    assert "earthengine authenticate" in str(excinfo.value)
    assert AUTHENTICATION_HINT.splitlines()[0] in str(excinfo.value)


def test_configuration_never_exposes_credentials():
    config = GEEConfig(
        enabled=True,
        service_account="robot@project.iam.gserviceaccount.com",
        credentials_path="/secret/key.json",
    )
    summary = config.public_summary()
    assert summary["auth_mode"] == "service_account"
    assert "/secret/key.json" not in str(summary)
    assert "robot@project.iam.gserviceaccount.com" not in str(summary)


def test_config_from_env_reads_expected_variables():
    config = GEEConfig.from_env(
        {
            "GEE_ENABLED": "true",
            "GEE_PROJECT": "geoia-carbon",
            "GEE_DEFAULT_BUFFER_HA": "250",
            "GEE_TIMEOUT_SECONDS": "45",
            "GEE_CACHE_TTL_SECONDS": "0",
        }
    )
    assert config.enabled is True
    assert config.project == "geoia-carbon"
    assert config.default_buffer_ha == 250.0
    assert config.timeout_seconds == 45
    assert config.cache_ttl_seconds == 0
    assert config.uses_service_account is False


# --- fallback ---------------------------------------------------------------

def test_null_provider_remains_functional_as_fallback():
    null = NullRemoteSensingProvider()
    traced = null.estimate_biomass(geometry={"type": "Polygon", "coordinates": []}, year=2024)
    assert traced.value is None
    assert traced.estimation_type is EstimationType.NOT_AVAILABLE
    assert null.estimate_land_cover(geometry={}, year=2024)["available"] is False


def test_real_provider_satisfies_the_same_protocol(aoi):
    """O provider real é substituível pelo nulo: mesma interface."""
    provider = make_provider(StubEarthEngineClient())
    for method in ("estimate_biomass", "estimate_canopy", "estimate_land_cover", "estimate_change"):
        assert hasattr(provider, method)
        assert hasattr(NullRemoteSensingProvider(), method)


# --- dossel -----------------------------------------------------------------

def test_canopy_returns_metric_and_sample_count(aoi):
    provider = make_provider(StubEarthEngineClient())
    canopy = provider.observe_canopy(aoi, 2024)
    assert canopy.available is True
    assert canopy.metric == "rh98"
    assert canopy.sample_count == 31
    assert canopy.mean_canopy_height_m == 18.4
    assert any("NÃO é convertida em biomassa" in w for w in canopy.warnings)


def test_canopy_failure_is_not_available(aoi):
    provider = make_provider(StubEarthEngineClient(fail={"canopy"}))
    canopy = provider.observe_canopy(aoi, 2024)
    assert canopy.available is False
    assert canopy.mean_canopy_height_m is None
