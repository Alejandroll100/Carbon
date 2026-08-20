"""Emissões operacionais no Brasil, separação de gases e GWP versionado.

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


# --- Emissões operacionais brasileiras e GWP ---------------------


def test_electricity_factor_is_year_specific_and_never_extrapolated(registry):
    resolver = FactorResolver(registry)
    got = resolver.resolve(
        "operational_emission_factor",
        purpose="eletricidade",
        level="electricity",
        year=2023,
        country="Brazil",
    )
    assert got.value == 0.0385
    assert got.gas == "CO2"
    assert got.unit == "tCO2/MWh"

    with pytest.raises(FactorNotFoundError):
        FactorResolver(registry).resolve(
            "operational_emission_factor",
            purpose="eletricidade",
            level="electricity",
            year=2026,
            country="Brazil",
        )


def test_diesel_never_resolves_to_the_electricity_factor(registry):
    """Regressão: sem escopo por fonte, o diesel usaria o fator da rede."""
    with pytest.raises(FactorNotFoundError):
        FactorResolver(registry).resolve(
            "operational_emission_factor", purpose="diesel", level="diesel"
        )


def test_gwp_sets_are_empty_and_refuse_to_invent_values():
    with pytest.raises(GWPNotAvailableError):
        to_co2e(1.0, "N2O", version="AR6")
    # CO2 é o próprio índice: vale 1 por definição, não por transcrição.
    assert to_co2e(5.0, "CO2", version="AR6") == (5.0, "AR6")


def test_gwp_versions_cannot_be_mixed():
    assert assert_single_gwp_version(["AR6", "AR6"]) == "AR6"
    with pytest.raises(GWPMixingError):
        assert_single_gwp_version(["AR5", "AR6"])


def test_n2o_chain_exposes_every_step_and_blocks_at_missing_ef1(registry):
    """N -> N2O-N -> N2O -> CO2e: nenhuma etapa escondida, e a cadeia para
    exatamente onde falta dado."""
    result = direct_n2o_from_nitrogen(10.0, FactorResolver(registry))
    assert result.available is False
    assert result.blocked_at == "EF1"
    assert result.n2o_n_t is None
    assert len(result.steps) == 4
    assert N2O_N_TO_N2O_RATIO == pytest.approx(44.0 / 28.0)
