"""Testes que reproduzem EXEMPLOS NUMÉRICOS das fontes primárias.

Cada teste cita documento, capítulo e seção. Se a base de fatores da GEØ.IA
estiver correta, ela tem de reproduzir a aritmética publicada pelo IPCC.
"""

from __future__ import annotations

import pytest

from carbon.factors.registry import FactorRegistry
from carbon.models.enums import ValidationStatus
from carbon.utils.units import CARBON_TO_CO2_RATIO


@pytest.fixture
def registry() -> FactorRegistry:
    return FactorRegistry.load_default()


# ---------------------------------------------------------------------------
# IPCC 2006 Vol.4 Cap.4, exemplo numérico das págs. 4.18-4.19
# País hipotético, zona temperada continental da Europa, pinus de 25 anos.
# ---------------------------------------------------------------------------


def test_ipcc_ch4_worked_example_biomass_gain(registry):
    """Reproduz: GTOTAL = GW x (1 + R); ΔCG = A x GTOTAL x CF.

    Valores do exemplo: GW = 4,0 t m.s./ha/ano (Tabela 4.9);
    R = 0,29 para AGB de 50 a 150 t/ha (Tabela 4.4);
    CF = 0,47 tC/t m.s. (Tabela 4.3); A = 100 000 ha.
    Resultado publicado: 242 520 tC/ano.
    """
    r = registry.get("RS_TEMPERATE_CONTINENTAL_AGB_50_150_SUPERSEDED_2006")
    cf = registry.get("CF_AGB_FOREST_IPCC2006")
    assert r.value == 0.29
    assert cf.value == 0.47
    assert r.agb_range_t_ha == [50.0, 150.0]

    gw = 4.0  # Tabela 4.9, não transcrita: entra como dado do exemplo
    g_total = gw * (1 + r.value)
    assert g_total == pytest.approx(5.16)

    delta_cg = 100_000 * g_total * cf.value
    assert delta_cg == pytest.approx(242_520.0)


def test_ipcc_ch4_worked_example_wood_removal(registry):
    """Reproduz Lwood-removals = H x BCEFR x (1 + R + BF) x CF = 725,16 tC/ano."""
    r = registry.get("RS_TEMPERATE_CONTINENTAL_AGB_50_150_SUPERSEDED_2006").value
    cf = registry.get("CF_AGB_FOREST_IPCC2006").value
    h, bcef_r, bf = 1_000.0, 1.11, 0.1
    assert h * bcef_r * (1 + r + bf) * cf == pytest.approx(725.16, abs=0.01)


def test_ipcc_ch4_worked_example_disturbance(registry):
    """Reproduz Ldisturbance = A x BW x (1 + R) x CF x fd = 1 455,12 tC/ano."""
    r = registry.get("RS_TEMPERATE_CONTINENTAL_AGB_50_150_SUPERSEDED_2006").value
    cf = registry.get("CF_AGB_FOREST_IPCC2006").value
    assert 2_000 * 4.0 * (1 + r) * cf * 0.3 == pytest.approx(1_455.12, abs=0.01)


# ---------------------------------------------------------------------------
# IPCC 2006 Vol.4 Cap.5, exemplo numérico da Seção 5.2.3.4
# Clima warm temperate, solo Mollisol (classe HAC), 1 Mha de cropland.
# ---------------------------------------------------------------------------


def test_ipcc_ch5_worked_example_soc_initial_stock(registry):
    """SOC_REF 88 tC/ha; 400 000 ha low input + full tillage e 600 000 ha
    medium input + full tillage. Resultado publicado: 58,78 milhões de tC."""
    soc_ref = registry.get("SOC_REF_WARM_TEMPERATE_MOIST_HAC").value
    f_lu = registry.get("FLU_LONG_TERM_CULTIVATED_TEMPERATE_BOREAL_MOIST").value
    f_mg = registry.get("FMG_FULL_TILLAGE_ALL_DRY_AND_MOIST_WET").value
    f_i_low = registry.get("FI_LOW_TEMPERATE_BOREAL_MOIST").value
    f_i_medium = registry.get("FI_MEDIUM_ALL_DRY_AND_MOIST_WET").value

    assert (soc_ref, f_lu, f_mg, f_i_low, f_i_medium) == (88.0, 0.69, 1.00, 0.92, 1.00)

    total = 400_000 * (soc_ref * f_lu * f_mg * f_i_low) + 600_000 * (
        soc_ref * f_lu * f_mg * f_i_medium
    )
    assert total / 1e6 == pytest.approx(58.78, abs=0.01)


def test_ipcc_ch5_worked_example_soc_final_stock_and_annual_change(registry):
    """Estoque final publicado: 64,06 milhões de tC; variação anual: 264 000 tC/ano."""
    soc_ref = registry.get("SOC_REF_WARM_TEMPERATE_MOIST_HAC").value
    f_lu = registry.get("FLU_LONG_TERM_CULTIVATED_TEMPERATE_BOREAL_MOIST").value
    full = registry.get("FMG_FULL_TILLAGE_ALL_DRY_AND_MOIST_WET").value
    reduced = registry.get("FMG_REDUCED_TILLAGE_TEMPERATE_BOREAL_MOIST").value
    no_till = registry.get("FMG_NO_TILL_TEMPERATE_BOREAL_MOIST").value
    low = registry.get("FI_LOW_TEMPERATE_BOREAL_MOIST").value
    medium = registry.get("FI_MEDIUM_ALL_DRY_AND_MOIST_WET").value

    assert (reduced, no_till) == (1.08, 1.15)

    initial = 400_000 * soc_ref * f_lu * full * low + 600_000 * soc_ref * f_lu * full * medium
    final = (
        200_000 * soc_ref * f_lu * full * low
        + 700_000 * soc_ref * f_lu * reduced * medium
        + 100_000 * soc_ref * f_lu * no_till * medium
    )
    assert final / 1e6 == pytest.approx(64.06, abs=0.01)
    # O IPCC publica "64,06 - 58,78 = 5,28 milhões / 20 anos = 264 000 tC/ano",
    # partindo dos totais JÁ ARREDONDADOS. A aritmética exata dá 264 132 tC/ano.
    # A diferença é o arredondamento da própria publicação, não erro de fator.
    assert (final - initial) / 1e6 == pytest.approx(5.28, abs=0.01)
    assert (final - initial) / 20 == pytest.approx(264_132.0, abs=1.0)
    assert (final - initial) / 20 == pytest.approx(264_000.0, rel=0.001)


def test_ipcc_ch5_worked_example_perennial_biomass(registry):
    """90 000 ha acumulando e 10 000 ha colhidos em clima tropical úmido.
    Perda publicada: 210 000 tC (10 000 ha x 21 tC/ha)."""
    stock = registry.get("AGB_C_PERENNIAL_TROPICAL_MOIST")
    assert stock.value == 21.0
    assert stock.unit == "tC/ha"
    assert stock.uncertainty_percent == 75.0
    assert 10_000 * stock.value == pytest.approx(210_000.0)


# ---------------------------------------------------------------------------
# Consistência da transcrição da Tabela 2.3 e da Tabela 5.5
# ---------------------------------------------------------------------------


def test_soc_ref_table_23_has_no_lac_for_boreal(registry):
    """A Tabela 2.3 marca 'NA' em LAC/boreal: o solo não ocorre normalmente ali.
    Ausência de linha é diferente de valor zero."""
    assert not registry.find(
        category="soil_organic_carbon_reference", climate_region="boreal", soil_type="LAC"
    )


def test_soc_ref_tropical_values_match_table_23(registry):
    expected = {
        ("tropical_dry", "HAC"): 38.0,
        ("tropical_dry", "LAC"): 35.0,
        ("tropical_dry", "sandy"): 31.0,
        ("tropical_moist", "HAC"): 65.0,
        ("tropical_moist", "LAC"): 47.0,
        ("tropical_moist", "sandy"): 39.0,
        ("tropical_wet", "HAC"): 44.0,
        ("tropical_wet", "LAC"): 60.0,
        ("tropical_wet", "sandy"): 66.0,
    }
    for (climate, soil), value in expected.items():
        factor = registry.get(f"SOC_REF_{climate.upper()}_{soil.upper()}")
        assert factor.value == value
        assert factor.unit == "tC/ha (0-30 cm)"
        assert factor.uncertainty_percent == 90.0  # nota da Tabela 2.3
        assert factor.reference_id == "IPCC2006_V4_CH2"


def test_wetland_soc_column_is_flagged_for_visual_check(registry):
    """A coluna de solos hidromórficos tem células mescladas: não pode ser usada
    antes de conferência visual do PDF."""
    for factor in registry.find(category="soil_organic_carbon_reference", soil_type="wetland"):
        assert factor.value is None
        assert factor.validation_status == ValidationStatus.REQUIRES_VALIDATION
        assert "mescladas" in (factor.notes or "")


def test_table_55_perennial_tree_crop_is_neutral(registry):
    """F_LU de cultivo perene/arbóreo é 1,00: o SOC de equilíbrio de um SAF
    consolidado iguala o de referência sob vegetação nativa."""
    factor = registry.get("FLU_PERENNIAL_TREE_CROP_ALL_DRY_AND_MOIST_WET")
    assert factor.value == 1.00
    assert factor.uncertainty_percent == 50.0
    assert factor.page_or_table == "Tabela 5.5"


def test_table_55_tropical_long_term_cultivation_loses_soc(registry):
    """Cultivo anual de longo prazo em trópico úmido reduz o SOC a 48% da
    referência — o resultado precisa reproduzir a direção do efeito."""
    assert registry.get("FLU_LONG_TERM_CULTIVATED_TROPICAL_MOIST_WET").value == 0.48


def test_organic_soil_emission_factors_match_table_56(registry):
    assert registry.get("EF_ORGANIC_SOIL_TROPICAL").value == 20.0
    assert registry.get("EF_ORGANIC_SOIL_WARM_TEMPERATE").value == 10.0
    assert registry.get("EF_ORGANIC_SOIL_BOREAL_COOL_TEMPERATE").value == 5.0
    for fid in (
        "EF_ORGANIC_SOIL_TROPICAL",
        "EF_ORGANIC_SOIL_WARM_TEMPERATE",
        "EF_ORGANIC_SOIL_BOREAL_COOL_TEMPERATE",
    ):
        assert registry.get(fid).uncertainty_percent == 90.0


# ---------------------------------------------------------------------------
# Frações de carbono por pool e uso da terra
# ---------------------------------------------------------------------------


def test_carbon_fraction_is_not_uniform_across_pools(registry):
    """O IPCC usa frações diferentes por pool. O motor não uniformiza em 0,47."""
    assert registry.get("CF_AGB_FOREST_IPCC2006").value == 0.47
    assert registry.get("CF_BIOMASS_CROPLAND_IPCC2006").value == 0.50
    assert registry.get("CF_DEADWOOD_IPCC2006").value == 0.50
    assert registry.get("CF_LITTER_FOREST_IPCC2006").value == 0.37
    assert registry.get("CF_LITTER_CROPLAND_IPCC2006").value == 0.40


def test_litter_carbon_fraction_differs_by_land_use(registry):
    forest = registry.find(category="carbon_fraction", pool="litter", land_use="natural_forest")
    cropland = registry.find(category="carbon_fraction", pool="litter", land_use="agroforestry")
    assert forest[0].value == 0.37
    assert cropland[0].value == 0.40


def test_carbon_to_co2_ratio_is_exact():
    """44/12 é razão de massa molar, não fator empírico: sem incerteza."""
    assert CARBON_TO_CO2_RATIO == 44.0 / 12.0
    assert 12.0 * CARBON_TO_CO2_RATIO == pytest.approx(44.0)
