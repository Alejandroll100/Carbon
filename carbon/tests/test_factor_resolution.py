"""Hierarquia de resolução, rastro, proxy e modo científico estrito.

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


# --- Resolução de fatores, proxy e modo científico estrito -------


def test_resolution_trace_records_alternatives_and_reason(registry):
    resolver = FactorResolver(registry)
    resolution = resolver.resolve(
        "soil_organic_carbon_reference",
        purpose="teste",
        climate_region="tropical_moist",
        soil_type="LAC",
    )
    trace = resolution.trace
    assert trace.resolved
    assert trace.selected_factor == "SOC_REF_TROPICAL_MOIST_LAC"
    assert trace.selection_reason
    assert trace.data_level == DataLevel.IPCC_DEFAULT
    assert trace.proxy is False
    assert trace.requested["climate_region"] == "tropical_moist"


def test_project_parameter_outranks_ipcc_default(registry):
    resolver = FactorResolver(
        registry,
        project_parameters={
            "carbon_fraction": ProjectParameter(
                value=0.52, unit="tC/t d.m.", source="laboratório do projeto"
            )
        },
    )
    resolution = resolver.resolve(
        "carbon_fraction", purpose="AGB", pool="aboveground_biomass", land_use="agroforestry"
    )
    assert resolution.value == 0.52
    assert resolution.data_level == DataLevel.PROJECT_SPECIFIC
    assert "precedência" in resolution.trace.selection_reason


def test_regional_factor_outranks_climate_default(registry):
    """Tabela 5.2 (regional) vence Tabela 5.1 (default climático) na hierarquia."""
    resolver = FactorResolver(registry)
    regional = resolver.resolve(
        "agb_biomass_density",
        purpose="AGB",
        land_use="agroforestry",
        region="South America",
        ecological_zone="humid_tropical_lowland",
    )
    assert regional.data_level == DataLevel.REGIONAL
    assert regional.value == 70.5


def test_proxy_requires_explicit_authorization(registry):
    """Sem autorização, o motor recusa; com autorização, marca proxy=True."""
    resolver = FactorResolver(registry)
    with pytest.raises(FactorNotFoundError):
        resolver.resolve(
            "root_to_shoot_ratio", purpose="BGB de SAF", land_use="agroforestry", agb_t_ha=70.0
        )

    authorized = FactorResolver(registry).resolve(
        "root_to_shoot_ratio",
        purpose="BGB de SAF",
        land_use="agroforestry",
        agb_t_ha=70.0,
        proxy=ProxyAuthorization(
            factor_id="RS_TROPICAL_MOIST_AMERICAS_NATURAL_LE125",
            justification=(
                "Floresta tropical úmida natural da América do Sul como classe análoga ao "
                "estrato arbóreo do SAF, sob responsabilidade técnica do projeto."
            ),
        ),
    )
    assert authorized.proxy is True
    assert authorized.data_level == DataLevel.SCIENTIFIC_PROXY
    assert authorized.value == 0.2845
    assert any("PROXY" in w for w in authorized.warnings)


def test_proxy_is_denied_in_strict_mode(registry):
    resolver = FactorResolver(registry, strict_factor_validation=True)
    with pytest.raises(ProxyNotAuthorizedError):
        resolver.resolve(
            "root_to_shoot_ratio",
            purpose="BGB de SAF",
            land_use="agroforestry",
            agb_t_ha=70.0,
            proxy=ProxyAuthorization(
                factor_id="RS_TROPICAL_MOIST_AMERICAS_NATURAL_LE125", justification="classe análoga"
            ),
        )


def test_proxy_caps_confidence_score(registry):
    """Proxy pesa mais contra a confiança do que fator não validado."""
    from carbon.core import confidence_engine

    config = CarbonEngineConfig(
        root_to_shoot_proxy=ProxyAuthorization(
            factor_id="RS_TROPICAL_MOIST_AMERICAS_NATURAL_LE125",
            justification="floresta tropical úmida da América do Sul como classe análoga",
        )
    )
    inventory = CarbonInventory(
        inventory_id="p",
        project_id="saf-br",
        year=2026,
        aboveground=BiomassObservation(dry_biomass_t_ha=70.0),
    )
    result = CarbonEngine(registry, config).calculate(saf_project(), inventory)

    assert result.proxy_used is True
    assert result.quality.confidence_score <= confidence_engine.PROXY_CAP
    assert any("PROXY" in p for p in result.quality.penalties)


def test_strict_mode_completes_a_fully_validated_scenario(registry):
    """Critério de pronto D: um cenário inteiramente validado roda em modo estrito.

    Todos os fatores usados (SOC_REF, F_LU/F_MG/F_I, CF de cropland, densidade
    regional de AGB) estão marcados 'validated' com referência e tabela.
    """
    engine = CarbonEngine(registry, CarbonEngineConfig(strict_factor_validation=True))
    result = engine.calculate(saf_project(), empty_inventory())

    assert result.carbon_stock.total_carbon_t == pytest.approx(3525.0 + 4700.0)
    assert result.proxy_used is False
    assert result.validation_warnings == []
    assert result.audit.strict_factor_validation is True
    assert result.audit.allow_scientific_proxy is False
    for entry in result.audit.factors_used:
        assert entry["validation_status"] in ("validated", "project_supplied")


# --- Ambiguidade ----------------------------------------------------------

def test_tie_between_equally_specific_factors_is_refused(registry):
    """Serapilheira tropical: folhosa decídua = 2,1 e conífera perene = 5,2.

    Sem ``forest_type``, os dois são igualmente específicos. Escolher por
    ordem alfabética daria 2,1 silenciosamente — o motor recusa e nomeia o
    critério que falta.
    """
    from carbon.services.factor_service import AmbiguousFactorError

    resolver = FactorResolver(registry)
    with pytest.raises(AmbiguousFactorError) as exc:
        resolver.resolve(
            "litter_carbon_stock",
            purpose="serapilheira",
            land_use="natural_forest",
            temperature_regime="tropical",
        )
    message = str(exc.value)
    assert "igualmente específicos" in message
    assert "LITTER_C_TROPICAL_BROADLEAF_DECIDUOUS=2.1" in message
    assert "LITTER_C_TROPICAL_NEEDLELEAF_EVERGREEN=5.2" in message


def test_supplying_the_missing_criterion_resolves_the_tie(registry):
    resolution = FactorResolver(registry).resolve(
        "litter_carbon_stock",
        purpose="serapilheira",
        land_use="natural_forest",
        temperature_regime="tropical",
        forest_type="broadleaf_deciduous",
    )
    assert resolution.value == 2.1


def test_amazon_forest_litter_is_unavailable_rather_than_subtropical(registry):
    """Regressão: o motor chegou a escolher serapilheira SUBTROPICAL para uma
    floresta amazônica, por empate resolvido em ordem alfabética."""
    from carbon.core.carbon_engine import CarbonEngine
    from carbon.models.enums import IPCCClimateRegion, LandUse

    project = saf_project(
        land_use=LandUse.NATURAL_FOREST,
        climate_region=IPCCClimateRegion.TROPICAL_WET,
        ecological_zone="tropical_rainforest",
        continent="North and South America",
        forest_origin="natural",
        forest_status="primary",
    )
    result = CarbonEngine(registry).calculate(project, empty_inventory())
    litter = result.carbon_stock.pools["litter"]
    assert litter.carbon_t.value is None
    assert "SUBTROPICAL" not in str(litter.carbon_t.factors_used)
