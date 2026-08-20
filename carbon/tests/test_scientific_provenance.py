"""Toda saída responde: de onde veio, com que fator, por qual equação.

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


# --- Proveniência científica -------------------------------------


def test_every_number_answers_where_it_came_from(registry):
    """Regra final: todo valor disponível responde origem, fator e equação."""
    result = CarbonEngine(registry).calculate(saf_project(), empty_inventory())

    for name in result.carbon_stock.available_pools:
        traced = result.carbon_stock.pools[name].carbon_t
        assert traced.estimation_type != EstimationType.NOT_AVAILABLE
        assert traced.source, f"{name} sem fonte"
        assert traced.factors_used or traced.equations_used, f"{name} sem fator nem equação"
        assert traced.inputs, f"{name} sem dados de entrada registrados"


def test_audit_carries_all_three_versions_plus_bibliography(registry):
    result = CarbonEngine(registry).calculate(saf_project(), empty_inventory())
    audit = result.audit
    assert audit.engine_version
    assert audit.factor_database_version == registry.version
    assert audit.methodology_version
    assert audit.reference_database_version == registry.references.version
    assert audit.resolution_traces


def test_every_used_factor_resolves_to_a_reference_entry(registry):
    result = CarbonEngine(registry).calculate(saf_project(), empty_inventory())
    for entry in result.audit.factors_used:
        if entry["reference_id"] is None:
            continue
        reference = registry.references.get(entry["reference_id"])
        assert reference.title
        assert reference.access_level in (
            "full_text_verified",
            "partial_text_verified",
            "metadata_only",
            "not_accessed",
        )


def test_sanity_checks_warn_without_rejecting(registry):
    """Estoque altíssimo gera aviso, não rejeição: pode ser real."""
    inventory = CarbonInventory(
        inventory_id="high",
        project_id="saf-br",
        year=2026,
        aboveground=BiomassObservation(dry_biomass_t_ha=3000.0),
    )
    result = CarbonEngine(registry).calculate(saf_project(), inventory)

    codes = {f["code"] for f in result.sanity_findings}
    assert "implausible_pool_density" in codes
    assert all(f["severity"] != "error" for f in result.sanity_findings)
    assert result.carbon_stock.total_carbon_t > 0  # resultado preservado


def test_sanity_flags_implausible_root_shoot(registry):
    inventory = CarbonInventory(
        inventory_id="rs",
        project_id="saf-br",
        year=2026,
        aboveground=BiomassObservation(dry_biomass_t_ha=50.0),
        belowground=BelowgroundObservation(dry_biomass_t_ha=100.0),
    )
    result = CarbonEngine(registry).calculate(saf_project(), inventory)
    assert "implausible_root_shoot" in {f["code"] for f in result.sanity_findings}
