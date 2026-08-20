"""Razão raiz:parte aérea (R): estratificação, ausência validada e proxy.

IPCC 2006 Vol.4 Cap.4, Tabela 4.4 (floresta) e Cap.5, Seção 5.2.1.2
(sistemas agrícolas).
"""

from __future__ import annotations

import pytest

from carbon.core import biomass_engine
from carbon.factors.registry import FactorRegistry
from carbon.models.enums import EstimationType, LandUse, ValidationStatus
from carbon.models.provenance import TracedValue
from carbon.services.factor_service import FactorResolver, ProxyAuthorization

from .conftest import saf_project


def test_root_shoot_stratum_does_not_apply_outside_its_agb_range(registry):
    """A Tabela 4.4 é estratificada por faixa de AGB: o estrato 50-150 não pode
    ser aplicado a uma floresta com 300 t/ha."""
    factor = registry.get("RS_TEMPERATE_CONTINENTAL_AGB_50_150_SUPERSEDED_2006")
    assert factor.applies_to_agb(100.0)
    assert not factor.applies_to_agb(300.0)
    assert not factor.applies_to_agb(20.0)
    assert not factor.applies_to_agb(None)

    assert registry.find(category="root_to_shoot_ratio", agb_t_ha=100.0)
    outside = registry.find(category="root_to_shoot_ratio", agb_t_ha=300.0)
    assert "RS_TEMPERATE_CONTINENTAL_AGB_50_150_SUPERSEDED_2006" not in [f.factor_id for f in outside]


def test_ipcc_declares_no_root_shoot_default_for_agricultural_systems(registry):
    """Cap.5, Seção 5.2.1.2: "Default values for below-ground biomass for
    agricultural systems are not available." Ausência VALIDADA, não lacuna."""
    factor = registry.get("RS_AGROFORESTRY_NO_IPCC_DEFAULT")
    assert factor.value is None
    assert factor.is_validated_absence
    assert not factor.requires_validation
    assert factor.reference_id == "IPCC2006_V4_CH5"
    assert "5.2.1.2" in factor.page_or_table
    assert "agroforestry" in factor.land_use


def test_agroforestry_bgb_is_refused_not_zero_filled(registry):
    """BGB de SAF sem medição vira not_available — jamais zero."""
    agb = TracedValue(value=7050.0, unit="t dry matter", estimation_type=EstimationType.MEASURED)
    resolver = FactorResolver(registry)
    bgb = biomass_engine.belowground_estimate(saf_project(), agb, None, resolver).dry_biomass

    assert bgb.value is None
    assert bgb.estimation_type == EstimationType.NOT_AVAILABLE
    assert "AUSÊNCIA VALIDADA" in bgb.notes[0]


def test_project_measured_ratio_outranks_everything(registry):
    """Medição do projeto tem precedência sobre qualquer default ou proxy."""
    from carbon.models.inventory import BelowgroundObservation

    agb = TracedValue(value=1000.0, unit="t dry matter", estimation_type=EstimationType.MEASURED)
    obs = BelowgroundObservation(root_to_shoot_ratio=0.31, root_to_shoot_source="escavação 2026")
    bgb = biomass_engine.belowground_estimate(
        saf_project(), agb, obs, FactorResolver(registry)
    ).dry_biomass

    assert bgb.value == pytest.approx(310.0)
    assert "PROJECT::root_to_shoot_ratio" in bgb.factors_used


def test_proxy_ratio_is_never_labelled_as_measurement(registry):
    """Proxy autorizado nunca se apresenta como medição direta."""
    agb = TracedValue(value=7050.0, unit="t dry matter", estimation_type=EstimationType.MEASURED)
    resolver = FactorResolver(registry)
    bgb = biomass_engine.belowground_estimate(
        saf_project(),
        agb,
        None,
        resolver,
        proxy=ProxyAuthorization(
            factor_id="RS_TROPICAL_MOIST_AMERICAS_NATURAL_LE125",
            justification="floresta tropical úmida da América do Sul como classe análoga",
        ),
    ).dry_biomass

    assert bgb.value == pytest.approx(7050.0 * 0.2845)
    assert bgb.estimation_type != EstimationType.MEASURED
    assert any("PROXY" in n for n in bgb.notes)
    assert resolver.used_proxy is True


@pytest.fixture
def registry() -> FactorRegistry:
    return FactorRegistry.load_default()


# --- Tabela 4.4 (Updated), Refinamento de 2019 ----------------------------

def test_2019_refinement_supersedes_the_2006_root_shoot_factor(registry):
    """Fator superado permanece auditável mas nunca é selecionado."""
    old = registry.get("RS_TEMPERATE_CONTINENTAL_AGB_50_150_SUPERSEDED_2006")
    assert old.is_superseded
    assert old.superseded_by == "IPCC2019R_V4_CH4"
    assert old.validation_status == ValidationStatus.VALIDATED  # continua verificado

    resolver = FactorResolver(registry)
    with pytest.raises(Exception):
        resolver.resolve(
            "root_to_shoot_ratio",
            purpose="não deve alcançar o fator de 2006",
            land_use="natural_forest",
            agb_t_ha=100.0,
            ecological_zone="temperate_continental_forest_2006",
        )


def test_south_american_natural_rainforest_resolves_without_proxy(registry):
    """Floresta amazônica: R agora vem de fator do domínio correto.

    Tabela 4.4 (Updated), tropical rainforest, América do Norte e do Sul,
    natural, AGB > 125 t/ha: R = 0,221 com SD de 0,036.
    """
    resolver = FactorResolver(registry)
    resolution = resolver.resolve(
        "root_to_shoot_ratio",
        purpose="BGB de floresta amazônica",
        land_use="natural_forest",
        agb_t_ha=307.1,
        ecological_zone="tropical_rainforest",
        continent="North and South America",
        origin="natural",
    )
    assert resolution.value == 0.221
    assert resolution.proxy is False
    assert resolution.reference_id == "IPCC2019R_V4_CH4"


def test_125_t_ha_threshold_selects_different_strata(registry):
    """O limiar de 125 t/ha da Tabela 4.4 tem de mudar o estrato escolhido."""
    common = dict(
        category="root_to_shoot_ratio",
        ecological_zone="tropical_dry",
        continent="North and South America",
        origin="natural",
    )
    below = registry.find(agb_t_ha=80.0, **common)[0]
    above = registry.find(agb_t_ha=200.0, **common)[0]
    assert below.value == 0.334
    assert above.value == 0.379
    assert below.factor_id != above.factor_id


def test_standard_deviation_is_not_confused_with_percent(registry):
    """A Tabela 4.4 mistura ±90% (default) com SD absoluto.

    Tratar SD 0,036 como '0,036%' ou como '36%' distorce a incerteza em ordens
    de grandeza. O motor converte explicitamente e registra o tipo original.
    """
    sd_factor = registry.get("RS_TROPICAL_RAINFOREST_AMERICAS_NATURAL_LE125")
    assert sd_factor.uncertainty_type == "standard_deviation"
    assert sd_factor.uncertainty_absolute == 0.036
    assert sd_factor.uncertainty_percent is None
    assert sd_factor.uncertainty_as_percent() == pytest.approx(0.036 / 0.221 * 100.0)

    default_factor = registry.get("RS_TROPICAL_RAINFOREST_AFRICA_NATURAL_LE125")
    assert default_factor.uncertainty_type == "default_90pct"
    assert default_factor.uncertainty_as_percent() == 90.0


def test_planted_and_natural_forests_get_different_ratios(registry):
    """Origem (natural vs plantada) é critério da Tabela 4.4, não detalhe."""
    common = dict(
        category="root_to_shoot_ratio",
        ecological_zone="tropical_rainforest",
        continent="North and South America",
        agb_t_ha=100.0,
    )
    natural = registry.find(origin="natural", **common)[0]
    planted = registry.find(origin="planted", **common)[0]
    assert natural.value == 0.221
    assert planted.value == 0.170
