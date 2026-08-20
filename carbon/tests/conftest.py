"""Fixtures compartilhadas dos testes científicos."""

from __future__ import annotations

import pytest

from carbon.factors.registry import FactorRegistry
from carbon.models.enums import CalculationMode, IPCCClimateRegion, IPCCSoilType, LandUse
from carbon.models.inventory import CarbonInventory
from carbon.models.project import CarbonProject, Coordinates


@pytest.fixture
def registry() -> FactorRegistry:
    return FactorRegistry.load_default()


def saf_project(**overrides) -> CarbonProject:
    """Projeto de referência: SAF de 100 ha no Vale do Ribeira (SP)."""
    base = dict(
        project_id="saf-br",
        name="SAF Brasil",
        country="Brazil",
        state="São Paulo",
        land_use=LandUse.AGROFORESTRY,
        area_ha=100.0,
        coordinates=Coordinates(lat=-24.497, lon=-47.844),
        reference_year=2026,
        climate_region=IPCCClimateRegion.TROPICAL_MOIST,
        soil_type=IPCCSoilType.LAC,
        region="South America",
        ecological_zone="humid_tropical_lowland",
    )
    base.update(overrides)
    return CarbonProject(**base)


def empty_inventory(year: int = 2026, inventory_id: str = "inv") -> CarbonInventory:
    return CarbonInventory(
        inventory_id=inventory_id,
        project_id="saf-br",
        year=year,
        mode=CalculationMode.QUICK_ESTIMATE,
    )
