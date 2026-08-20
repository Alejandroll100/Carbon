"""Endpoint REST geoespacial, com provider mockado (sem Earth Engine real)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from carbon.api import routes
from carbon.app import app
from carbon.models.enums import LandUse
from carbon.services.gee_cache import GEEQueryCache
from carbon.services.gee_provider import GoogleEarthEngineCarbonProvider
from carbon.services.geospatial_analysis import (
    GeospatialAnalysisInput,
    GeospatialCarbonService,
)
from carbon.tests.gee_stubs import (
    StubEarthEngineClient,
    gedi_payload,
    land_cover_payload,
    sentinel_payload,
)

RIBEIRA_LAT = -24.497
RIBEIRA_LON = -47.844

PAYLOAD = {
    "lat": RIBEIRA_LAT,
    "lon": RIBEIRA_LON,
    "area_ha": 100.0,
    "current_year": 2024,
    "baseline_year": 2020,
    "land_use": "agroforestry",
    "country": "Brazil",
    "state": "São Paulo",
    "climate_region": "tropical_moist",
    "region": "South America",
    "ecological_zone": "humid_tropical_lowland",
}


def build_service(client: StubEarthEngineClient, **kwargs) -> GeospatialCarbonService:
    provider = GoogleEarthEngineCarbonProvider(
        client, cache=GEEQueryCache(ttl_seconds=0), **kwargs
    )
    return GeospatialCarbonService(provider)


@pytest.fixture
def stub_client() -> StubEarthEngineClient:
    return StubEarthEngineClient(
        gedi_by_year={
            2020: gedi_payload(sample_count=35, mean=100.0, start="2020-03-01", end="2020-10-01"),
            2024: gedi_payload(sample_count=40, mean=120.0),
        }
    )


@pytest.fixture
def client(stub_client) -> TestClient:
    service = build_service(stub_client)
    app.dependency_overrides[routes.get_geospatial_service] = lambda: service
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# --- endpoint ---------------------------------------------------------------

def test_analyze_endpoint_returns_the_documented_sections(client):
    response = client.post("/api/carbon/geospatial/analyze", json=PAYLOAD)
    assert response.status_code == 200
    body = response.json()
    for section in (
        "input",
        "geometry",
        "remote_sensing",
        "carbon",
        "quality",
        "provenance",
        "warnings",
    ):
        assert section in body
    for block in ("biomass", "canopy", "land_cover", "vegetation_indices", "change"):
        assert block in body["remote_sensing"]
    assert body["result_type"] == "remote_sensing_supported_carbon_estimate"


def test_calculate_alias_matches_analyze(client):
    analyze = client.post("/api/carbon/geospatial/analyze", json=PAYLOAD).json()
    calculate = client.post("/api/carbon/geospatial/calculate", json=PAYLOAD).json()
    assert (
        analyze["carbon"]["audit"]["input_fingerprint"]
        == calculate["carbon"]["audit"]["input_fingerprint"]
    )


def test_existing_routes_are_untouched(client):
    """As 13 rotas anteriores continuam respondendo."""
    assert client.get("/api/carbon/factors").status_code == 200
    assert client.get("/api/carbon/methodologies").status_code == 200
    created = client.post(
        "/api/carbon/projects",
        json={
            "name": "regressão",
            "land_use": "agroforestry",
            "area_ha": 10.0,
            "coordinates": {"lat": RIBEIRA_LAT, "lon": RIBEIRA_LON},
            "reference_year": 2026,
        },
    )
    assert created.status_code == 201


def test_datasets_endpoint_declares_the_scientific_rules(client):
    body = client.get("/api/carbon/geospatial/datasets").json()
    ids = [d["dataset_id"] for d in body["datasets"]]
    assert "LARSE/GEDI/GEDI04_A_002_MONTHLY" in ids
    assert "COPERNICUS/S2_SR_HARMONIZED" in ids
    assert any("nunca é convertido em carbono" in rule for rule in body["scientific_rules"])
    assert "crédito" in body["disclaimer"].lower()
    # Configuração exposta sem credencial.
    assert "credentials_path" not in body["configuration"]


def test_invalid_payload_is_rejected_with_422(client):
    response = client.post(
        "/api/carbon/geospatial/analyze",
        json={"lat": RIBEIRA_LAT, "lon": RIBEIRA_LON, "current_year": 2024},
    )
    assert response.status_code == 422


def test_polygon_payload_is_accepted(client):
    from carbon.services.geometry_service import circular_buffer_polygon, equivalent_radius_m

    polygon = circular_buffer_polygon(RIBEIRA_LAT, RIBEIRA_LON, equivalent_radius_m(75.0))
    response = client.post(
        "/api/carbon/geospatial/analyze",
        json={
            "geometry": polygon,
            "current_year": 2024,
            "land_use": "natural_forest",
        },
    )
    assert response.status_code == 200
    geometry = response.json()["geometry"]
    assert geometry["geometry_source"] == "user_polygon"
    assert geometry["geometry_area_ha"] == pytest.approx(75.0, rel=0.01)


# --- reprodutibilidade ------------------------------------------------------

def test_same_input_yields_stable_fingerprint(stub_client):
    service = build_service(stub_client)
    request = GeospatialAnalysisInput(**PAYLOAD)
    first = service.analyze(request)
    second = service.analyze(request)
    assert (
        first["carbon"]["audit"]["input_fingerprint"]
        == second["carbon"]["audit"]["input_fingerprint"]
    )
    assert first["geometry"]["geometry_hash"] == second["geometry"]["geometry_hash"]


# --- ciência no fluxo completo ---------------------------------------------

def test_carbon_comes_from_the_engine_not_from_the_provider(stub_client):
    service = build_service(stub_client)
    body = service.analyze(GeospatialAnalysisInput(**PAYLOAD))
    agb = body["carbon"]["carbon_stock"]["pools"]["aboveground_biomass"]
    assert agb["dry_biomass_t"]["value"] == pytest.approx(12_000.0)
    fraction = agb["carbon_t"]["inputs"]["carbon_fraction"]
    assert agb["carbon_t"]["value"] == pytest.approx(12_000.0 * fraction)


def test_change_is_computed_by_the_engine_from_two_inventories(stub_client):
    service = build_service(stub_client)
    body = service.analyze(GeospatialAnalysisInput(**PAYLOAD))
    change = body["carbon"]["change"]
    assert change is not None
    assert change["baseline_year"] == 2020
    assert change["current_year"] == 2024
    # 120 - 100 Mg/ha em 100 ha = 2000 t de matéria seca a mais.
    assert change["delta_carbon_t"] > 0
    assert body["remote_sensing"]["change"]["carbon_change_available"] is True


def test_baseline_outside_gedi_period_does_not_produce_carbon_change(stub_client):
    service = build_service(stub_client)
    body = service.analyze(
        GeospatialAnalysisInput(**{**PAYLOAD, "baseline_year": 2010})
    )
    assert body["remote_sensing"]["baseline_biomass"]["coverage_status"] == (
        "outside_temporal_coverage"
    )
    assert body["carbon"]["change"] is None
    assert any("2010" in w for w in body["warnings"])


def test_water_dominated_aoi_refuses_to_compute_biomass_silently():
    client = StubEarthEngineClient(
        land_cover=land_cover_payload(counts={"water": 9600.0, "trees": 400.0})
    )
    service = build_service(client)
    body = service.analyze(
        GeospatialAnalysisInput(
            **{**PAYLOAD, "land_use": LandUse.NATURAL_FOREST, "baseline_year": None}
        )
    )
    consistency = body["remote_sensing"]["consistency"]
    assert consistency["blocking"] is True
    decision = body["remote_sensing"]["source_decision"]
    assert decision["selected"] == "unavailable"
    assert body["quality"]["remote_sensing_support"]["remote_sensing_support_score"] == 0


def test_no_footprints_produces_no_carbon_from_satellite():
    client = StubEarthEngineClient(gedi=gedi_payload(sample_count=0, mean=None))
    service = build_service(client)
    body = service.analyze(
        GeospatialAnalysisInput(**{**PAYLOAD, "baseline_year": None})
    )
    biomass = body["remote_sensing"]["biomass"]
    assert biomass["available"] is False
    assert biomass["agb_total_t"] is None
    decision = body["remote_sensing"]["source_decision"]
    assert decision["delegated_to_engine"] is True
    pools = body["carbon"]["carbon_stock"]["pools"]
    for pool in pools.values():
        assert pool["carbon_t"]["value"] != 0


def test_low_support_caps_the_remote_sensing_score():
    client = StubEarthEngineClient(gedi=gedi_payload(sample_count=6))
    service = build_service(client)
    body = service.analyze(GeospatialAnalysisInput(**{**PAYLOAD, "baseline_year": None}))
    support = body["quality"]["remote_sensing_support"]
    assert support["remote_sensing_support_score"] <= 40
    assert any("suporte amostral" in p.lower() for p in support["penalties"])


def test_satellite_origin_does_not_inflate_engine_confidence(stub_client):
    service = build_service(stub_client)
    body = service.analyze(GeospatialAnalysisInput(**PAYLOAD))
    quality = body["quality"]
    assert quality["engine_confidence"]["confidence_score"] < 100
    # Os dois indicadores são distintos e ambos aparecem.
    assert "remote_sensing_support_score" in quality["remote_sensing_support"]
    assert quality["engine_confidence"]["confidence_score"] != (
        quality["remote_sensing_support"]["remote_sensing_support_score"]
    )


def test_cloud_free_scenes_absent_still_yields_carbon_from_gedi():
    """Nuvem no Sentinel não impede a biomassa lidar: são fontes independentes."""
    client = StubEarthEngineClient(
        sentinel=sentinel_payload(scene_count=0, ndvi=None, valid_fraction=None)
    )
    service = build_service(client)
    body = service.analyze(GeospatialAnalysisInput(**{**PAYLOAD, "baseline_year": None}))
    assert body["remote_sensing"]["vegetation_indices"]["available"] is False
    assert body["remote_sensing"]["biomass"]["available"] is True
    support = body["quality"]["remote_sensing_support"]
    assert any("nuvem" in p.lower() for p in support["penalties"])


def test_provenance_section_lists_datasets_and_observations(stub_client):
    service = build_service(stub_client)
    body = service.analyze(GeospatialAnalysisInput(**PAYLOAD))
    provenance = body["provenance"]
    assert provenance["observations"]["biomass"]["dataset_id"]
    assert provenance["observations"]["land_cover"]["dataset_id"]
    assert provenance["audit"]["input_fingerprint"]
    assert len(provenance["datasets"]) >= 5


def test_result_is_never_called_a_carbon_credit(stub_client):
    service = build_service(stub_client)
    body = service.analyze(GeospatialAnalysisInput(**PAYLOAD))

    methodology = body["carbon"]["methodology"]
    assert "Carbon Credit Potential" in methodology["not_implemented"]
    assert "Verified Carbon Credits" in methodology["not_implemented"]

    # Fora da lista de NÃO implementados, nenhuma dessas expressões pode
    # aparecer: o resultado não se apresenta como crédito em lugar nenhum.
    payload = dict(body)
    payload["carbon"] = {
        key: value for key, value in body["carbon"].items() if key != "methodology"
    }
    blob = str(payload).lower()
    for forbidden in (
        "verified carbon credit",
        "certified carbon credit",
        "sellable credit",
        "crédito comercializável válido",
    ):
        assert forbidden not in blob
    assert body["result_type"] == "remote_sensing_supported_carbon_estimate"
