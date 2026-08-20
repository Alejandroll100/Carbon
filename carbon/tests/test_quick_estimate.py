"""quick_estimate: estimativa a partir de área, uso da terra, clima e solo.

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


# --- quick_estimate ----------------------------------------------


def test_quick_estimate_runs_for_brazilian_agroforestry(registry):
    """Área + uso da terra + região climática + solo produzem estimativa real."""
    result = CarbonEngine(registry).calculate(saf_project(), empty_inventory())

    stock = result.carbon_stock
    assert stock is not None
    assert stock.total_carbon_t is not None and stock.total_carbon_t > 0
    # AGB: Tabela 5.2, América do Sul, agrossilvicultural = 70,5 t m.s./ha
    #      x 100 ha x CF de cropland 0,50 = 3525 tC
    assert stock.pools["aboveground_biomass"].carbon_t.value == pytest.approx(3525.0)
    assert stock.pools["soil_organic_carbon"].carbon_t.value == pytest.approx(4700.0)
    assert stock.status == ResultStatus.PARTIAL
    assert result.status != ResultStatus.FAILED


def test_quick_estimate_declares_every_default_factor_it_used(registry):
    result = CarbonEngine(registry).calculate(saf_project(), empty_inventory())
    agb = result.carbon_stock.pools["aboveground_biomass"].carbon_t

    assert agb.estimation_type == EstimationType.DEFAULT_FACTOR
    assert "AGB_DM_AGROSILVI_SAMERICA_HUMID_LOW" in agb.factors_used
    assert "CF_BIOMASS_CROPLAND_IPCC2006" in agb.factors_used
    assert "estimated_from_default_factor" in agb.notes


def test_quick_estimate_still_refuses_belowground(registry):
    """Rodar quick_estimate não pode fabricar BGB: o IPCC declara que não há
    default para sistemas agrícolas."""
    result = CarbonEngine(registry).calculate(saf_project(), empty_inventory())
    bgb = result.carbon_stock.pools["belowground_biomass"]

    assert bgb.carbon_t.value is None
    assert "belowground_biomass" in result.missing_data
    assert any(u["category"] == "root_to_shoot_ratio" for u in result.unresolved_factors)


def test_quick_estimate_blocked_without_climate_region(registry):
    """Sem região climática, o SOC Tier 1 não roda — e o motor diz o porquê."""
    project = saf_project(climate_region=None, soil_type=None)
    result = CarbonEngine(registry).calculate(project, empty_inventory())
    soil = result.carbon_stock.pools["soil_organic_carbon"]
    assert soil.carbon_t.value is None
    assert "climate_region" in soil.carbon_t.notes[0]


def test_quick_estimate_never_reports_full_stock(registry):
    """Com pools ausentes, o total não pode ser apresentado como estoque completo."""
    result = CarbonEngine(registry).calculate(saf_project(), empty_inventory())
    assert set(result.carbon_stock.missing_pools) >= {
        "belowground_biomass",
        "deadwood",
        "litter",
    }
    assert any(i.type == "data_gap" for i in result.insights)
