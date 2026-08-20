"""Testes de API — fluxo completo projeto -> inventário -> cálculo."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from carbon.api import routes
from carbon.app import app
from carbon.services.project_repository import InMemoryCarbonRepository


@pytest.fixture
def client() -> TestClient:
    repo = InMemoryCarbonRepository()
    app.dependency_overrides[routes.get_repository] = lambda: repo
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


PROJECT = {
    "project_id": "geoia-carbon-001",
    "name": "SAF Fazenda Teste",
    "country": "Brazil",
    "state": "São Paulo",
    "municipality": "Registro",
    "land_use": "agroforestry",
    "area_ha": 125.4,
    "coordinates": {"lat": -24.497, "lon": -47.844},
    "reference_year": 2026,
    "baseline_year": 2024,
    "climate_domain": "tropical",
}


def _inventory(year: int, agb: float, inventory_id: str) -> dict:
    return {
        "inventory_id": inventory_id,
        "year": year,
        "mode": "inventory",
        "aboveground": {"dry_biomass_t": agb, "uncertainty_percent": 12.0},
        "belowground": {"root_to_shoot_ratio": 0.24, "uncertainty_percent": 30.0},
        "soil": {
            "depth_cm": 30.0,
            "bulk_density_g_cm3": 1.2,
            "organic_carbon_percent": 2.4,
            "uncertainty_percent": 25.0,
        },
    }


def test_full_flow(client: TestClient):
    r = client.post("/api/carbon/projects", json=PROJECT)
    assert r.status_code == 201
    pid = r.json()["project_id"]

    assert client.post(f"/api/carbon/projects/{pid}/inventory", json=_inventory(2024, 4000.0, "inv-2024")).status_code == 201
    assert client.post(f"/api/carbon/projects/{pid}/inventory", json=_inventory(2026, 4800.0, "inv-2026")).status_code == 201

    r = client.post(
        f"/api/carbon/projects/{pid}/calculate",
        json={"inventory_id": "inv-2026", "baseline_inventory_id": "inv-2024"},
    )
    assert r.status_code == 200
    body = r.json()

    assert body["carbon_stock"]["total_carbon_t"] > 0
    assert body["carbon_stock"]["pools"]["deadwood"]["carbon_t"]["value"] is None
    assert body["change"]["delta_carbon_t"] > 0
    assert body["removal"]["period_years"] == 2
    assert body["net_balance"]["gross_removals_tCO2e"] is not None
    assert body["quality"]["confidence_score"] > 0
    assert body["audit"]["engine_version"]
    assert body["audit"]["factors_used"]
    assert "crédito" in body["disclaimer"]

    r = client.get(f"/api/carbon/projects/{pid}/results")
    assert r.status_code == 200
    assert r.json()["audit"]["calculation_id"] == body["audit"]["calculation_id"]

    r = client.get(f"/api/carbon/projects/{pid}/balance")
    assert r.status_code == 200
    assert set(r.json()) >= {"land_carbon", "operational_emissions", "net_carbon_balance"}


def test_duplicate_inventory_rejected(client: TestClient):
    client.post("/api/carbon/projects", json=PROJECT)
    pid = PROJECT["project_id"]
    client.post(f"/api/carbon/projects/{pid}/inventory", json=_inventory(2026, 100.0, "inv-x"))
    r = client.post(f"/api/carbon/projects/{pid}/inventory", json=_inventory(2026, 200.0, "inv-x"))
    assert r.status_code == 409


def test_soil_endpoint_creates_new_revision(client: TestClient):
    client.post("/api/carbon/projects", json=PROJECT)
    pid = PROJECT["project_id"]
    inv = _inventory(2026, 1000.0, "inv-s")
    inv.pop("soil")
    client.post(f"/api/carbon/projects/{pid}/inventory", json=inv)

    r = client.post(
        f"/api/carbon/projects/{pid}/soil",
        json={
            "inventory_id": "inv-s",
            "soil": {"depth_cm": 30, "bulk_density_g_cm3": 1.1, "organic_carbon_percent": 1.8},
        },
    )
    assert r.status_code == 201
    assert r.json()["revision"] == 2
    assert r.json()["supersedes"] == "inv-s"

    history = client.get(f"/api/carbon/projects/{pid}/inventories").json()
    assert len(history) == 2
    assert history[0]["soil"] is None


def test_trees_endpoint_requires_plot_area(client: TestClient):
    client.post("/api/carbon/projects", json=PROJECT)
    pid = PROJECT["project_id"]
    client.post(f"/api/carbon/projects/{pid}/inventory", json=_inventory(2026, 1000.0, "inv-t"))

    r = client.post(
        f"/api/carbon/projects/{pid}/trees",
        json={
            "inventory_id": "inv-t",
            "trees": [
                {
                    "dbh_cm": 32.5,
                    "height_m": 18.4,
                    "wood_density_g_cm3": 0.6,
                    "equation_id": "CHAVE2014_MOIST_H",
                }
            ],
        },
    )
    assert r.status_code == 422


def test_invalid_coordinates_rejected_by_api(client: TestClient):
    payload = dict(PROJECT, project_id="bad", coordinates={"lat": 200.0, "lon": 0.0})
    r = client.post("/api/carbon/projects", json=payload)
    assert r.status_code == 422


def test_factors_endpoint_exposes_pending_validation(client: TestClient):
    r = client.get("/api/carbon/factors")
    assert r.status_code == 200
    body = r.json()
    assert body["pending_validation"]
    assert body["without_value"]
    assert body["validated_absence"], "a base precisa expor ausências validadas"
    for factor in body["factors"]:
        # Todo fator declara unidade e, se validado, aponta bibliografia.
        assert factor["unit"]
        if factor["validation_status"] == "validated":
            assert factor["reference_id"]
            assert factor["page_or_table"]


def test_methodologies_endpoint_declares_scope(client: TestClient):
    body = client.get("/api/carbon/methodologies").json()
    assert "Carbon Stock Estimate" in body["implemented_scope"]
    assert "Verified Carbon Credits" in body["not_implemented"]
    assert body["allometric_equations"]


def test_unknown_project_returns_404(client: TestClient):
    assert client.get("/api/carbon/projects/nao-existe").status_code == 404
    assert client.get("/api/carbon/projects/nao-existe/results").status_code == 404
