"""Constrói ``carbon/factors/defaults.json`` a partir das tabelas transcritas.

Cada bloco abaixo corresponde a UMA tabela de UMA fonte primária, com o
ponteiro exato (documento, capítulo, tabela). Manter este script é a forma de
manter a transcrição auditável: o JSON é artefato derivado, este arquivo é a
transcrição revisável.

Executar:  python -m scripts.build_factor_database
"""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "carbon" / "factors" / "defaults.json"

VERSION = "2026.03"
VALIDATED_BY = "GEØ.IA — leitura direta do documento primário (web_fetch)"
VALIDATED_AT = "2026-08-13"

factors: list[dict] = []


def add(**kw) -> None:
    base = {
        "value": None,
        "gas": None,
        "pool": None,
        "country": None,
        "region": None,
        "climate_region": None,
        "temperature_regime": None,
        "moisture_regime": None,
        "ecological_zone": None,
        "soil_type": None,
        "land_use": [],
        "forest_type": None,
        "vegetation_type": None,
        "species": None,
        "agb_range_t_ha": None,
        "year": None,
        "factor_kind": None,
        "level": None,
        "value_range": None,
        "uncertainty_percent": None,
        "validated_by": None,
        "validated_at": None,
        "notes": None,
        "version": VERSION,
    }
    base.update(kw)
    factors.append(base)


def validated(**kw) -> None:
    add(validation_status="validated", validated_by=VALIDATED_BY, validated_at=VALIDATED_AT, **kw)


# ---------------------------------------------------------------------------
# FRAÇÕES DE CARBONO
# ---------------------------------------------------------------------------
# IPCC 2006 Vol.4 Cap.4, Tabela 4.3 — valor citado três vezes no exemplo
# numérico das págs. 4.18-4.19: "CF = 0.47 tonne C (tonne d.m.)-1 (Table 4.3)".
validated(
    factor_id="CF_AGB_FOREST_IPCC2006",
    category="carbon_fraction",
    value=0.47,
    unit="tC/t d.m.",
    pool="aboveground_biomass",
    land_use=["natural_forest", "secondary_forest", "planted_forest", "reforestation", "forest_restoration"],
    tier=1,
    data_level="ipcc_default",
    methodology="IPCC 2006 Tier 1",
    reference_id="IPCC2006_V4_CH4",
    page_or_table="Tabela 4.3; valor citado no exemplo numérico das págs. 4.18-4.19",
    notes=(
        "A Tabela 4.3 completa é estratificada e não pôde ser lida (extração do PDF trunca "
        "antes da Seção 4.5). Este é o valor genérico de floresta usado pelo próprio IPCC no "
        "exemplo do capítulo. Incerteza não disponível no trecho acessível."
    ),
)
# Mesma fração aplicada à BGB: Equação 2.12/2.13 do Cap.2 aplica um único CF ao
# termo (1 + R), ou seja, à biomassa total lenhosa.
validated(
    factor_id="CF_BGB_FOREST_IPCC2006",
    category="carbon_fraction",
    value=0.47,
    unit="tC/t d.m.",
    pool="belowground_biomass",
    land_use=["natural_forest", "secondary_forest", "planted_forest", "reforestation", "forest_restoration"],
    tier=1,
    data_level="ipcc_default",
    methodology="IPCC 2006 Tier 1",
    reference_id="IPCC2006_V4_CH4",
    page_or_table="Tabela 4.3 via Equações 2.12-2.14 do Cap.2, que aplicam CF ao termo (1+R)",
    notes="O IPCC aplica a mesma CF à biomassa lenhosa total (aérea + subterrânea) nas Eqs. 2.12-2.14.",
)
# IPCC 2006 Vol.4 Cap.5, Seção 5.2.1.4 (Passo 4) e nota da Tabela 5.8:
# "default carbon density of 0.5 tonne C/tonne biomass" para cropland.
validated(
    factor_id="CF_BIOMASS_CROPLAND_IPCC2006",
    category="carbon_fraction",
    value=0.50,
    unit="tC/t d.m.",
    pool="aboveground_biomass",
    land_use=["cropland", "agroforestry", "silvopastoral"],
    tier=1,
    data_level="ipcc_default",
    methodology="IPCC 2006 Tier 1",
    reference_id="IPCC2006_V4_CH5",
    page_or_table="Seção 5.2.1.4, Passo 4; e nota da Tabela 5.8",
    notes=(
        "DIVERGÊNCIA INTERNA DO IPCC, deliberadamente preservada: o Cap.4 usa 0,47 para "
        "floresta e o Cap.5 usa 0,50 para cropland/agrofloresta. O motor escolhe pelo uso da "
        "terra em vez de uniformizar."
    ),
)
validated(
    factor_id="CF_BGB_CROPLAND_IPCC2006",
    category="carbon_fraction",
    value=0.50,
    unit="tC/t d.m.",
    pool="belowground_biomass",
    land_use=["cropland", "agroforestry", "silvopastoral"],
    tier=1,
    data_level="ipcc_default",
    methodology="IPCC 2006 Tier 1",
    reference_id="IPCC2006_V4_CH5",
    page_or_table="Seção 5.2.1.4, Passo 4; via Equações 2.9-2.14 do Cap.2",
    notes=(
        "O Cap.5 enuncia 0,50 no contexto de biomassa aérea, mas remete às Equações 2.9-2.14 do "
        "Cap.2, que aplicam uma única CF ao termo (1+R) — isto é, à biomassa lenhosa total. "
        "Extensão ao pool subterrâneo por essa via, não por analogia solta."
    ),
)

# IPCC 2006 Vol.4 Cap.5, Seção 5.2.2.2 e 5.2.2.4 (Passo 3):
# "0.50 for dead wood and 0.40 for litter".
validated(
    factor_id="CF_DEADWOOD_IPCC2006",
    category="carbon_fraction",
    value=0.50,
    unit="tC/t d.m.",
    pool="deadwood",
    tier=1,
    data_level="ipcc_default",
    methodology="IPCC 2006 Tier 1",
    reference_id="IPCC2006_V4_CH5",
    page_or_table="Seção 5.2.2.2 e Seção 5.2.2.4, Passo 3",
)
validated(
    factor_id="CF_LITTER_CROPLAND_IPCC2006",
    category="carbon_fraction",
    value=0.40,
    unit="tC/t d.m.",
    pool="litter",
    land_use=["cropland", "agroforestry", "silvopastoral"],
    tier=1,
    data_level="ipcc_default",
    methodology="IPCC 2006 Tier 1",
    reference_id="IPCC2006_V4_CH5",
    page_or_table="Seção 5.2.2.4, Passo 3",
)
# IPCC 2006 Vol.4 Cap.2, Equação 2.19: "CF = carbon fraction of dry matter
# (default = 0.37 for litter)"; confirmado na nota de fonte da Tabela 2.2.
validated(
    factor_id="CF_LITTER_FOREST_IPCC2006",
    category="carbon_fraction",
    value=0.37,
    unit="tC/t d.m.",
    pool="litter",
    land_use=["natural_forest", "secondary_forest", "planted_forest", "reforestation", "forest_restoration"],
    tier=1,
    data_level="ipcc_default",
    methodology="IPCC 2006 Tier 1",
    reference_id="IPCC2006_V4_CH2",
    page_or_table="Equação 2.19 (definição de CF) e nota de fonte da Tabela 2.2",
    notes="0,37 (contexto florestal, Cap.2) difere de 0,40 (contexto cropland, Cap.5). Escopo por uso da terra.",
)

# ---------------------------------------------------------------------------
# RAZÃO RAIZ:PARTE AÉREA (R)
# ---------------------------------------------------------------------------
# IPCC 2006 Vol.4 Cap.4, Tabela 4.4 — único estrato acessível, citado no
# exemplo numérico das págs. 4.18-4.19 (floresta de pinus, zona temperada
# continental da Europa): "R = 0.29 ... for above-ground biomass of 50 to 150 t ha-1".
validated(
    factor_id="RS_TEMPERATE_CONTINENTAL_AGB_50_150_SUPERSEDED_2006",
    category="root_to_shoot_ratio",
    value=0.29,
    unit="t BGB / t AGB",
    pool="belowground_biomass",
    climate_region="cold_temperate_moist",
    ecological_zone="temperate_continental_forest_2006",
    forest_type="conifer",
    land_use=[],
    agb_range_t_ha=[50.0, 150.0],
    tier=1,
    data_level="ipcc_default",
    methodology="IPCC 2006 Tier 1",
    reference_id="IPCC2006_V4_CH4",
    page_or_table="Tabela 4.4; estrato citado no exemplo numérico das págs. 4.18-4.19",
    superseded_by="IPCC2019R_V4_CH4",
    notes=(
        "SUPERADO pela Tabela 4.4 (Updated) do Refinamento de 2019, transcrita integralmente. "
        "Mantido apenas para reproduzir o exemplo numérico das págs. 4.18-4.19 do documento de "
        "2006 nos testes de regressão. NÃO deve ser resolvido em produção: por isso não declara "
        "land_use, e a resolução por uso da terra nunca o alcança."
    ),
)
# Ausência validada: IPCC 2006 Vol.4 Cap.5, Seção 5.2.1.2, "Below-ground biomass
# accumulation / Tier 1": "The default assumption is that there is no change in
# below-ground biomass of perennial trees in agricultural systems. Default values
# for below-ground biomass for agricultural systems are not available."
add(
    factor_id="RS_AGROFORESTRY_NO_IPCC_DEFAULT",
    category="root_to_shoot_ratio",
    value=None,
    unit="t BGB / t AGB",
    pool="belowground_biomass",
    land_use=["agroforestry", "silvopastoral", "cropland"],
    tier=1,
    data_level="ipcc_default",
    methodology="IPCC 2006 Tier 1",
    validation_status="no_default_available",
    validated_by=VALIDATED_BY,
    validated_at=VALIDATED_AT,
    reference_id="IPCC2006_V4_CH5",
    page_or_table="Seção 5.2.1.2, 'Below-ground biomass accumulation', Tier 1",
    notes=(
        "AUSÊNCIA VALIDADA, não lacuna por falta de pesquisa. O IPCC declara textualmente que "
        "não existem valores default de biomassa subterrânea para sistemas agrícolas e que o "
        "Tier 1 assume variação nula. O Tier 2 exige razões empíricas específicas de região ou "
        "tipo de vegetação. Portanto: BGB de SAF exige medição, parâmetro do projeto, fonte "
        "regional revisada por pares, ou proxy explicitamente autorizado."
    ),
)


# ---------------------------------------------------------------------------
# TABELA 4.4 (UPDATED) — RAZÃO RAIZ:PARTE AÉREA (R)
# IPCC 2019 Refinement, Vol.4 Cap.4. SUBSTITUI a Tabela 4.4 de 2006.
# Unidade: t raiz m.s. / t parte aérea m.s. Limiar de estrato: 125 t AGB/ha.
# Zonas ecológicas conformes à FAO Global Ecological Zones (FRA 2015).
# Transcrição: apenas os domínios Tropical, Subtropical e Boreal. O domínio
# Temperado tem estratos adicionais por espécie que NÃO foram transcritos.
# ---------------------------------------------------------------------------
TABLE_4_4_2019 = [
    # (zona ecológica, continente, origem, faixa AGB, R, incerteza, tipo)
    ("tropical_rainforest", "Africa", "natural", (None, 125.0), 0.825, 90.0, "default_90pct"),
    ("tropical_rainforest", "Africa", "natural", (125.0, None), 0.532, 90.0, "default_90pct"),
    ("tropical_rainforest", "North and South America", "natural", (None, 125.0), 0.221, 0.036, "standard_deviation"),
    ("tropical_rainforest", "North and South America", "planted", (None, 125.0), 0.170, 0.11, "standard_deviation"),
    ("tropical_rainforest", "North and South America", "natural", (125.0, None), 0.221, 0.036, "standard_deviation"),
    ("tropical_rainforest", "North and South America", "planted", (125.0, None), 0.170, 0.11, "standard_deviation"),
    ("tropical_rainforest", "Asia", "natural", (None, 125.0), 0.207, 0.072, "standard_deviation"),
    ("tropical_rainforest", "Asia", "planted", (None, 125.0), 0.325, 0.025, "standard_deviation"),
    ("tropical_rainforest", "Asia", "natural", (125.0, None), 0.212, 0.077, "standard_deviation"),
    ("tropical_moist", "Africa", "natural", (None, 125.0), 0.232, 90.0, "default_90pct"),
    ("tropical_moist", "Africa", "natural", (125.0, None), 0.232, 90.0, "default_90pct"),
    ("tropical_moist", "North and South America", "natural", (None, 125.0), 0.2845, 0.061, "standard_deviation"),
    ("tropical_moist", "North and South America", "natural", (125.0, None), 0.284, 0.061, "standard_deviation"),
    ("tropical_moist", "Asia", "natural", (None, 125.0), 0.323, 0.073, "standard_deviation"),
    ("tropical_moist", "Asia", "natural", (125.0, None), 0.246, 0.036, "standard_deviation"),
    ("tropical_dry", "Africa", "natural", (None, 125.0), 0.332, 0.247, "standard_deviation"),
    ("tropical_dry", "Africa", "natural", (125.0, None), 0.379, 0.040, "standard_deviation"),
    ("tropical_dry", "North and South America", "natural", (None, 125.0), 0.334, 0.040, "standard_deviation"),
    ("tropical_dry", "North and South America", "natural", (125.0, None), 0.379, 0.040, "standard_deviation"),
    ("tropical_dry", "Asia", "natural", (None, 125.0), 0.440, 90.0, "default_90pct"),
    ("tropical_dry", "Asia", "natural", (125.0, None), 0.379, 0.040, "standard_deviation"),
    ("tropical_mountain", "North and South America", "natural", (None, 125.0), 0.348, 90.0, "default_90pct"),
    ("tropical_mountain", "North and South America", "planted", (None, 125.0), 0.205, 90.0, "default_90pct"),
    ("tropical_mountain", "North and South America", "natural", (125.0, None), 0.283, 0.16, "standard_deviation"),
    ("tropical_mountain", "Asia", "natural", (None, 125.0), 0.322, 0.084, "standard_deviation"),
    ("tropical_mountain", "Asia", "natural", (125.0, None), 0.345, 0.280, "standard_deviation"),
    ("subtropical_humid", "Africa", "natural", (None, 125.0), 0.232, 90.0, "default_90pct"),
    ("subtropical_humid", "Africa", "natural", (125.0, None), 0.232, 90.0, "default_90pct"),
    ("subtropical_humid", "North and South America", "natural", (None, 125.0), 0.175, 90.0, "default_90pct"),
    ("subtropical_humid", "North and South America", "natural", (125.0, None), 0.284, 90.0, "default_90pct"),
    ("subtropical_humid", "Asia", "natural", (None, 125.0), 0.230, 90.0, "default_90pct"),
    ("subtropical_humid", "Asia", "natural", (125.0, None), 0.246, 90.0, "default_90pct"),
    ("subtropical_dry", "North and South America", "natural", (None, 125.0), 0.336, 90.0, "default_90pct"),
    ("subtropical_dry", "North and South America", "natural", (125.0, None), 0.352, 0.047, "standard_deviation"),
    ("subtropical_dry", "Asia", "natural", (None, 125.0), 0.440, 0.184, "standard_deviation"),
    ("subtropical_dry", "Asia", "natural", (125.0, None), 0.440, 0.184, "standard_deviation"),
    ("subtropical_steppe", "North and South America", "natural", (None, 125.0), 1.338, 90.0, "default_90pct"),
    ("subtropical_steppe", "Asia", "natural", (125.0, None), 1.338, 90.0, "default_90pct"),
    ("subtropical_steppe", "Asia", "planted", (None, 125.0), 2.158, 90.0, "default_90pct"),
    ("boreal_coniferous_tundra_mountain", None, None, (None, 75.0), 0.390, None, "range"),
    ("boreal_coniferous_tundra_mountain", None, None, (75.0, None), 0.240, None, "range"),
]
#: Sigla curta e legível para o continente nos identificadores de fator.
CONTINENT_SLUG = {
    "North and South America": "AMERICAS",
    "Africa": "AFRICA",
    "Asia": "ASIA",
    "Europe": "EUROPE",
    "Oceania": "OCEANIA",
    None: "ALL",
}
FOREST_LAND_USES = [
    "natural_forest", "secondary_forest", "planted_forest", "reforestation", "forest_restoration",
]
for zone, continent, origin, agb_range, value, unc, unc_type in TABLE_4_4_2019:
    low, high = agb_range
    tag = "LE125" if high == 125.0 else ("GT125" if low == 125.0 else ("LE75" if high == 75.0 else "GT75"))
    parts = [zone.upper(), CONTINENT_SLUG[continent], (origin or "ANY").upper(), tag]
    land_use = FOREST_LAND_USES
    if origin == "planted":
        land_use = ["planted_forest", "reforestation"]
    elif origin == "natural":
        land_use = ["natural_forest", "secondary_forest", "forest_restoration"]
    validated(
        factor_id="RS_" + "_".join(parts),
        category="root_to_shoot_ratio",
        value=value,
        unit="t BGB / t AGB",
        pool="belowground_biomass",
        ecological_zone=zone,
        continent=continent,
        origin=origin,
        land_use=land_use,
        agb_range_t_ha=[low, high],
        tier=1,
        data_level="biome_specific" if continent else "ipcc_default",
        uncertainty_percent=unc if unc_type == "default_90pct" else None,
        uncertainty_absolute=unc if unc_type == "standard_deviation" else None,
        uncertainty_type=unc_type,
        methodology="IPCC 2019 Refinement, Tier 1",
        reference_id="IPCC2019R_V4_CH4",
        page_or_table="Tabela 4.4 (Updated), págs. 4.18-4.21",
        notes=(
            "Estratos boreais reportam FAIXA (0,23-0,96 e 0,15-0,37), não desvio-padrão; "
            "incerteza não convertida."
            if unc_type == "range"
            else None
        ),
    )

# ---------------------------------------------------------------------------
# TABELA 4.7 (UPDATED) — BIOMASSA AÉREA EM FLORESTAS NATURAIS (t m.s./ha)
# IPCC 2019 Refinement, Vol.4 Cap.4. Incerteza em SD absoluto.
# Transcrição: domínios Tropical e Subtropical. Temperado e Boreal não transcritos.
# ---------------------------------------------------------------------------
TABLE_4_7_2019 = [
    ("tropical_rainforest", "Africa", "primary", 404.2, 120.4),
    ("tropical_rainforest", "Africa", "secondary_over_20y", 212.9, 143.1),
    ("tropical_rainforest", "Africa", "secondary_up_to_20y", 52.8, 35.6),
    ("tropical_rainforest", "North and South America", "primary", 307.1, 104.9),
    ("tropical_rainforest", "North and South America", "secondary_over_20y", 206.4, 80.4),
    ("tropical_rainforest", "North and South America", "secondary_up_to_20y", 75.7, 34.5),
    ("tropical_rainforest", "Asia", "primary", 413.1, 128.5),
    ("tropical_rainforest", "Asia", "secondary_over_20y", 131.6, 20.7),
    ("tropical_rainforest", "Asia", "secondary_up_to_20y", 45.6, 20.6),
    ("tropical_moist_deciduous", "Africa", "primary", 236.6, 104.7),
    ("tropical_moist_deciduous", "North and South America", "primary", 187.3, 94.0),
    ("tropical_moist_deciduous", "North and South America", "secondary_over_20y", 131.0, 54.2),
    ("tropical_moist_deciduous", "North and South America", "secondary_up_to_20y", 55.7, 28.7),
    ("tropical_dry", "North and South America", "primary", 127.5, 72.6),
    ("tropical_dry", "North and South America", "secondary_over_20y", 118.9, 81.3),
    ("tropical_dry", "North and South America", "secondary_up_to_20y", 32.2, 24.2),
    ("tropical_shrubland", "North and South America", "secondary_over_20y", 71.5, 46.4),
    ("tropical_mountain", "North and South America", "primary", 195.0, 95.6),
    ("tropical_mountain", "North and South America", "secondary_over_20y", 184.4, 111.0),
    ("tropical_mountain", "North and South America", "secondary_up_to_20y", 75.9, 51.1),
    ("subtropical_humid", "North and South America", "secondary_over_20y", 84.5, 42.9),
    ("subtropical_dry", "North and South America", "secondary_over_20y", 115.9, 46.2),
    ("subtropical_steppe", "North and South America", "secondary_over_20y", 44.0, 26.0),
    ("subtropical_mountain", "North and South America", "secondary_over_20y", 74.6, 40.1),
]
STATUS_TO_LAND_USE = {
    "primary": ["natural_forest"],
    "secondary_over_20y": ["secondary_forest", "natural_forest", "forest_restoration", "reforestation"],
    "secondary_up_to_20y": ["secondary_forest", "forest_restoration", "reforestation"],
}
for zone, continent, status, value, sd in TABLE_4_7_2019:
    validated(
        factor_id=f"AGB_DM_{zone.upper()}_{CONTINENT_SLUG[continent]}_{status.upper()}",
        category="agb_biomass_density",
        value=value,
        unit="t d.m./ha",
        pool="aboveground_biomass",
        ecological_zone=zone,
        continent=continent,
        status_condition=status,
        origin="natural",
        land_use=STATUS_TO_LAND_USE[status],
        tier=1,
        data_level="biome_specific",
        uncertainty_absolute=sd,
        uncertainty_type="standard_deviation",
        methodology="IPCC 2019 Refinement, Tier 1",
        reference_id="IPCC2019R_V4_CH4",
        page_or_table="Tabela 4.7 (Updated), págs. 4.22-4.25",
        notes=(
            "Floresta primária = antiga, intacta ou sem intervenção humana ativa; secundária = "
            "todas as demais. A tabela assume definição de floresta com pelo menos 10% de "
            "cobertura de copa."
        ),
    )

# ---------------------------------------------------------------------------
# TABELA 4.9 (UPDATED) — CRESCIMENTO LÍQUIDO DE BIOMASSA AÉREA (t m.s./ha/ano)
# IPCC 2019 Refinement, Vol.4 Cap.4. Transcrição: América do Norte e do Sul.
# "Crescimento LÍQUIDO": já contabiliza produtividade E mortalidade.
# ---------------------------------------------------------------------------
TABLE_4_9_2019_AMERICAS = [
    ("tropical_rainforest", "primary", 1.0, 2.0),
    ("tropical_rainforest", "secondary_over_20y", 2.3, 1.1),
    ("tropical_rainforest", "secondary_up_to_20y", 5.9, 2.5),
    ("tropical_moist_deciduous", "primary", 0.4, 2.1),
    ("tropical_moist_deciduous", "secondary_over_20y", 2.7, 1.7),
    ("tropical_moist_deciduous", "secondary_up_to_20y", 5.2, 2.3),
    ("tropical_dry", "secondary_over_20y", 1.6, 1.1),
    ("tropical_dry", "secondary_up_to_20y", 3.9, 2.4),
    ("tropical_mountain", "primary", 0.5, 1.9),
    ("tropical_mountain", "secondary_over_20y", 1.8, 0.8),
    ("tropical_mountain", "secondary_up_to_20y", 4.4, 1.6),
]
for zone, status, value, sd in TABLE_4_9_2019_AMERICAS:
    validated(
        factor_id=f"AGB_GROWTH_{zone.upper()}_NSAMERICA_{status.upper()}",
        category="agb_net_growth",
        value=value,
        unit="t d.m./ha/ano",
        pool="aboveground_biomass",
        ecological_zone=zone,
        continent="North and South America",
        status_condition=status,
        land_use=STATUS_TO_LAND_USE[status],
        tier=1,
        data_level="biome_specific",
        uncertainty_absolute=sd,
        uncertainty_type="standard_deviation",
        methodology="IPCC 2019 Refinement, Tier 1",
        reference_id="IPCC2019R_V4_CH4",
        page_or_table="Tabela 4.9 (Updated), págs. 4.34-4.38",
        notes=(
            "Crescimento LÍQUIDO: a nota 1 da tabela define que produtividade e mortalidade já "
            "estão contabilizadas. Não somar mortalidade separadamente. Vários desvios-padrão "
            "excedem a média (ex.: primária 1,0 ± 2,0), o que indica que o valor central não "
            "distingue crescimento de perda com confiança."
        ),
    )

# ---------------------------------------------------------------------------
# TABELA 4.8 (UPDATED) — AGB EM PLANTIOS FLORESTAIS (t m.s./ha) — Américas
# ---------------------------------------------------------------------------
TABLE_4_8_2019_AMERICAS = [
    ("tropical_rainforest", "Eucalyptus sp.", None, 200.0),
    ("tropical_rainforest", "Pinus sp.", None, 300.0),
    ("tropical_rainforest", "Other Broadleaf", None, 150.0),
    ("tropical_rainforest", "Tectona grandis", "over_20y", 240.0),
    ("tropical_moist_deciduous", "Eucalyptus sp.", "over_20y", 90.0),
    ("tropical_moist_deciduous", "Pinus sp.", "over_20y", 270.0),
    ("tropical_moist_deciduous", "Other Broadleaf", None, 100.0),
    ("tropical_moist_deciduous", "Swietenia macrophylla", "up_to_20y", 94.0),
    ("tropical_moist_deciduous", "Swietenia macrophylla", "over_20y", 121.0),
    ("tropical_moist_deciduous", "Tectona grandis", "up_to_20y", 84.0),
    ("tropical_moist_deciduous", "Tectona grandis", "over_20y", 284.0),
    ("tropical_dry", "Eucalyptus sp.", None, 90.0),
    ("tropical_dry", "Pinus sp.", None, 110.0),
    ("tropical_dry", "Other Broadleaf", None, 60.0),
    ("tropical_dry", "Tectona grandis", None, 90.0),
]
for zone, species, age, value in TABLE_4_8_2019_AMERICAS:
    slug = species.replace(" ", "_").replace(".", "").upper()
    validated(
        factor_id=f"AGB_DM_PLANTATION_{zone.upper()}_AMERICAS_{slug}" + (f"_{age.upper()}" if age else ""),
        category="agb_biomass_density",
        value=value,
        unit="t d.m./ha",
        pool="aboveground_biomass",
        ecological_zone=zone,
        continent="North and South America",
        species=species,
        origin="planted",
        level=age,
        land_use=["planted_forest", "reforestation"],
        tier=1,
        data_level="species_specific",
        uncertainty_percent=90.0,
        uncertainty_type="default_90pct",
        methodology="IPCC 2019 Refinement, Tier 1",
        reference_id="IPCC2019R_V4_CH4",
        page_or_table="Tabela 4.8 (Updated), págs. 4.26-4.33",
        notes="Plantio maduro. Fonte original da linha: IPCC 2003 (GPG-LULUCF).",
    )

# ---------------------------------------------------------------------------
# DENSIDADE DE BIOMASSA / CARBONO AÉREO — quick_estimate
# ---------------------------------------------------------------------------
# IPCC 2006 Vol.4 Cap.5, Tabela 5.1 (fonte primária: Schroeder 1994).
# Unidade: tonnes C ha-1 (JÁ em carbono, não matéria seca). Erro +75%.
for fid, temp, moist, stock, cycle, growth in [
    ("AGB_C_PERENNIAL_TEMPERATE", "temperate", None, 63.0, 30, 2.1),
    ("AGB_C_PERENNIAL_TROPICAL_DRY", "tropical", "dry", 9.0, 5, 1.8),
    ("AGB_C_PERENNIAL_TROPICAL_MOIST", "tropical", "moist", 21.0, 8, 2.6),
    ("AGB_C_PERENNIAL_TROPICAL_WET", "tropical", "wet", 50.0, 5, 10.0),
]:
    validated(
        factor_id=fid,
        category="agb_carbon_density",
        value=stock,
        unit="tC/ha",
        pool="aboveground_biomass",
        temperature_regime=temp,
        moisture_regime=moist,
        land_use=["agroforestry", "silvopastoral", "cropland"],
        tier=1,
        data_level="ipcc_default",
        uncertainty_percent=75.0,
        methodology="IPCC 2006 Tier 1",
        reference_id="IPCC2006_V4_CH5",
        page_or_table="Tabela 5.1",
        notes=(
            f"Estoque de carbono aéreo NO MOMENTO DA COLHEITA, ciclo de colheita/maturidade "
            f"{cycle} anos, taxa de acumulação {growth} tC/ha/ano. Representa o teto do ciclo, "
            f"não a média — sistema jovem tem estoque menor. Fonte primária: Schroeder (1994)."
        ),
    )

# IPCC 2006 Vol.4 Cap.5, Tabela 5.2 (fonte primária: Albrecht & Kandji 2003).
# Unidade: tonnes ha-1 de biomassa aérea (matéria seca).
for fid, region, eco, system, val, low, high in [
    ("AGB_DM_AGROSILVI_SAMERICA_HUMID_LOW", "South America", "humid_tropical_lowland", "agrosilvicultural", 70.5, 39, 102),
    ("AGB_DM_AGROSILVI_SAMERICA_DRY_LOWLANDS", "South America", "dry_lowlands", "agrosilvicultural", 117.0, 39, 195),
    ("AGB_DM_AGROSILVI_AFRICA_HUMID_HIGH", "Africa", "humid_tropical_highland", "agrosilvicultural", 41.0, 29, 53),
]:
    validated(
        factor_id=fid,
        category="agb_biomass_density",
        value=val,
        unit="t d.m./ha",
        pool="aboveground_biomass",
        region=region,
        ecological_zone=eco,
        vegetation_type=system,
        land_use=["agroforestry"],
        tier=1,
        data_level="regional",
        value_range=[float(low), float(high)],
        methodology="IPCC 2006 Tier 1 (compilação regional)",
        reference_id="IPCC2006_V4_CH5",
        page_or_table="Tabela 5.2",
        notes=(
            "Rotulado pelo IPCC como 'potential C storage' — capacidade potencial de "
            "armazenamento do sistema, não estoque medido de uma área específica. A tabela não "
            "reporta incerteza estatística, apenas faixa observada. Fonte primária: Albrecht & "
            "Kandji (2003)."
        ),
    )

# IPCC 2006 Vol.4 Cap.5, Tabela 5.9 — biomassa após UM ano da conversão.
for fid, temp, moist, val in [
    ("AGB_C_YEAR1_ANNUAL_CROP", None, None, 5.0),
    ("AGB_C_YEAR1_PERENNIAL_TEMPERATE", "temperate", None, 2.1),
    ("AGB_C_YEAR1_PERENNIAL_TROPICAL_DRY", "tropical", "dry", 1.8),
    ("AGB_C_YEAR1_PERENNIAL_TROPICAL_MOIST", "tropical", "moist", 2.6),
    ("AGB_C_YEAR1_PERENNIAL_TROPICAL_WET", "tropical", "wet", 10.0),
]:
    validated(
        factor_id=fid,
        category="agb_carbon_year1_after_conversion",
        value=val,
        unit="tC/ha",
        pool="aboveground_biomass",
        temperature_regime=temp,
        moisture_regime=moist,
        land_use=["cropland", "agroforestry"],
        tier=1,
        data_level="ipcc_default",
        uncertainty_percent=75.0,
        methodology="IPCC 2006 Tier 1",
        reference_id="IPCC2006_V4_CH5",
        page_or_table="Tabela 5.9",
        notes="Vale apenas para o primeiro ano após conversão. Não usar como estoque de sistema estabelecido.",
    )

# ---------------------------------------------------------------------------
# SOC_REF — IPCC 2006 Vol.4 Cap.2, Tabela 2.3 (tC/ha, 0-30 cm)
# Incerteza nominal declarada na nota da tabela: ±90% (2 desvios-padrão).
# ---------------------------------------------------------------------------
SOC_REF_TABLE = {
    # climate_region: {soil_type: (valor, from_1996_guidelines)}
    "boreal": {"HAC": (68, False), "LAC": None, "sandy": (10, True), "spodic": (117, False), "volcanic": (20, True)},
    "cold_temperate_dry": {"HAC": (50, False), "LAC": (33, False), "sandy": (34, False), "spodic": None, "volcanic": (20, True)},
    "cold_temperate_moist": {"HAC": (95, False), "LAC": (85, False), "sandy": (71, False), "spodic": (115, False), "volcanic": (130, False)},
    "warm_temperate_dry": {"HAC": (38, False), "LAC": (24, False), "sandy": (19, False), "spodic": None, "volcanic": (70, True)},
    "warm_temperate_moist": {"HAC": (88, False), "LAC": (63, False), "sandy": (34, False), "spodic": None, "volcanic": (80, False)},
    "tropical_dry": {"HAC": (38, False), "LAC": (35, False), "sandy": (31, False), "spodic": None, "volcanic": (50, True)},
    "tropical_moist": {"HAC": (65, False), "LAC": (47, False), "sandy": (39, False), "spodic": None, "volcanic": (70, True)},
    "tropical_wet": {"HAC": (44, False), "LAC": (60, False), "sandy": (66, False), "spodic": None, "volcanic": (130, True)},
    "tropical_montane": {"HAC": (88, False), "LAC": (63, False), "sandy": (34, False), "spodic": None, "volcanic": (80, False)},
}
MONTANE_NOTE = (
    "Nota * da Tabela 2.3: não havia dados para estimar diretamente o clima tropical montano; "
    "os valores foram baseados na região warm temperate moist."
)
for climate, soils in SOC_REF_TABLE.items():
    for soil, entry in soils.items():
        if entry is None:
            continue  # 'NA' na tabela: solo não ocorre normalmente nessa zona
        value, from_1996 = entry
        note_parts = []
        if from_1996:
            note_parts.append(
                "Nota # da Tabela 2.3: sem dados disponíveis; valor default das Diretrizes IPCC 1996 foi mantido."
            )
        if climate == "tropical_montane":
            note_parts.append(MONTANE_NOTE)
        validated(
            factor_id=f"SOC_REF_{climate.upper()}_{soil.upper()}",
            category="soil_organic_carbon_reference",
            value=float(value),
            unit="tC/ha (0-30 cm)",
            pool="soil_organic_carbon",
            climate_region=climate,
            soil_type=soil,
            tier=1,
            data_level="ipcc_default",
            uncertainty_percent=90.0,
            methodology="IPCC 2006 Tier 1",
            reference_id="IPCC2006_V4_CH2",
            page_or_table="Tabela 2.3",
            notes=" ".join(note_parts) or None,
        )

# Coluna 'wetland soils' da Tabela 2.3: células mescladas por grupo climático na
# extração de texto. Registrada como pendente de conferência VISUAL.
for climate in ("boreal", "cold_temperate_dry", "cold_temperate_moist", "warm_temperate_dry",
                "warm_temperate_moist", "tropical_dry", "tropical_moist", "tropical_wet"):
    add(
        factor_id=f"SOC_REF_{climate.upper()}_WETLAND",
        category="soil_organic_carbon_reference",
        value=None,
        unit="tC/ha (0-30 cm)",
        pool="soil_organic_carbon",
        climate_region=climate,
        soil_type="wetland",
        tier=1,
        data_level="ipcc_default",
        uncertainty_percent=90.0,
        validation_status="REQUIRES_VALIDATION",
        reference_id="IPCC2006_V4_CH2",
        page_or_table="Tabela 2.3, coluna 'Wetland soils'",
        notes=(
            "A coluna de solos hidromórficos usa células mescladas por grupo climático. A "
            "extração de texto retornou 4 valores (146, 87, 88, 86) para 9 linhas, sem indicar "
            "com segurança o alinhamento. Exige conferência VISUAL do PDF antes de uso. "
            "Gleissolos brasileiros caem nesta classe."
        ),
    )

# ---------------------------------------------------------------------------
# FATORES DE MUDANÇA DE ESTOQUE DO SOLO — IPCC 2006 Vol.4 Cap.5, Tabela 5.5
# Valores relativos, período de referência D = 20 anos, profundidade 0-30 cm.
# ---------------------------------------------------------------------------
TABLE_5_5 = [
    # (factor_kind, level, temperature_regime, moisture_regime, value, uncertainty)
    ("FLU", "long_term_cultivated", "temperate_boreal", "dry", 0.80, 9),
    ("FLU", "long_term_cultivated", "temperate_boreal", "moist", 0.69, 12),
    ("FLU", "long_term_cultivated", "tropical", "dry", 0.58, 61),
    ("FLU", "long_term_cultivated", "tropical", "moist_wet", 0.48, 46),
    ("FLU", "long_term_cultivated", "tropical_montane", None, 0.64, 50),
    ("FLU", "paddy_rice", "all", "dry_and_moist_wet", 1.10, 50),
    ("FLU", "perennial_tree_crop", "all", "dry_and_moist_wet", 1.00, 50),
    ("FLU", "set_aside", "temperate_boreal_and_tropical", "dry", 0.93, 11),
    ("FLU", "set_aside", "temperate_boreal_and_tropical", "moist_wet", 0.82, 17),
    ("FLU", "set_aside", "tropical_montane", None, 0.88, 50),
    ("FMG", "full_tillage", "all", "dry_and_moist_wet", 1.00, None),
    ("FMG", "reduced_tillage", "temperate_boreal", "dry", 1.02, 6),
    ("FMG", "reduced_tillage", "temperate_boreal", "moist", 1.08, 5),
    ("FMG", "reduced_tillage", "tropical", "dry", 1.09, 9),
    ("FMG", "reduced_tillage", "tropical", "moist_wet", 1.15, 8),
    ("FMG", "reduced_tillage", "tropical_montane", None, 1.09, 50),
    ("FMG", "no_till", "temperate_boreal", "dry", 1.10, 5),
    ("FMG", "no_till", "temperate_boreal", "moist", 1.15, 4),
    ("FMG", "no_till", "tropical", "dry", 1.17, 8),
    ("FMG", "no_till", "tropical", "moist_wet", 1.22, 7),
    ("FMG", "no_till", "tropical_montane", None, 1.16, 50),
    ("FI", "low", "temperate_boreal", "dry", 0.95, 13),
    ("FI", "low", "temperate_boreal", "moist", 0.92, 14),
    ("FI", "low", "tropical", "dry", 0.95, 13),
    ("FI", "low", "tropical", "moist_wet", 0.92, 14),
    ("FI", "low", "tropical_montane", None, 0.94, 50),
    ("FI", "medium", "all", "dry_and_moist_wet", 1.00, None),
    ("FI", "high_without_manure", "temperate_boreal_and_tropical", "dry", 1.04, 13),
    ("FI", "high_without_manure", "temperate_boreal_and_tropical", "moist_wet", 1.11, 10),
    ("FI", "high_without_manure", "tropical_montane", None, 1.08, 50),
    ("FI", "high_with_manure", "temperate_boreal_and_tropical", "dry", 1.37, 12),
    ("FI", "high_with_manure", "temperate_boreal_and_tropical", "moist_wet", 1.44, 13),
    ("FI", "high_with_manure", "tropical_montane", None, 1.41, 50),
]
for kind, level, temp, moist, value, unc in TABLE_5_5:
    suffix = f"{temp}_{moist}" if moist else temp
    validated(
        factor_id=f"{kind}_{level}_{suffix}".upper(),
        category="soil_stock_change_factor",
        value=value,
        unit="dimensionless",
        pool="soil_organic_carbon",
        factor_kind=kind,
        level=level,
        temperature_regime=temp,
        moisture_regime=moist,
        land_use=["cropland", "agroforestry", "silvopastoral"],
        tier=1,
        data_level="ipcc_default",
        uncertainty_percent=float(unc) if unc is not None else None,
        methodology="IPCC 2006 Tier 1 (D = 20 anos, 0-30 cm)",
        reference_id="IPCC2006_V4_CH5",
        page_or_table="Tabela 5.5",
        notes=(
            "Valor de referência definido (incerteza refletida nos estoques de referência)."
            if unc is None
            else "Erro = 2 desvios-padrão como % da média; ±50% indica ausência de estudos suficientes (julgamento de especialista)."
        ),
    )

# ---------------------------------------------------------------------------
# SERAPILHEIRA — IPCC 2006 Vol.4 Cap.2, Tabela 2.2 (tC/ha, florestas maduras)
# ---------------------------------------------------------------------------
for fid, climate, ftype, value, rng in [
    ("LITTER_C_TROPICAL_BROADLEAF_DECIDUOUS", "tropical", "broadleaf_deciduous", 2.1, [1.0, 3.0]),
    ("LITTER_C_TROPICAL_NEEDLELEAF_EVERGREEN", "tropical", "needleleaf_evergreen", 5.2, None),
    ("LITTER_C_SUBTROPICAL_BROADLEAF_DECIDUOUS", "subtropical", "broadleaf_deciduous", 2.8, [2.0, 3.0]),
    ("LITTER_C_SUBTROPICAL_NEEDLELEAF_EVERGREEN", "subtropical", "needleleaf_evergreen", 4.1, None),
]:
    validated(
        factor_id=fid,
        category="litter_carbon_stock",
        value=value,
        unit="tC/ha",
        pool="litter",
        temperature_regime=climate,
        forest_type=ftype,
        land_use=["natural_forest", "secondary_forest", "planted_forest", "forest_restoration", "reforestation"],
        tier=1,
        data_level="ipcc_default",
        value_range=rng,
        methodology="IPCC 2006 Tier 1",
        reference_id="IPCC2006_V4_CH2",
        page_or_table="Tabela 2.2",
        notes=(
            "Estoque de FLORESTA MADURA. A nota da tabela adverte que estes valores NÃO incluem "
            "detritos lenhosos finos (< 10 cm), sendo portanto incompletos face à definição IPCC "
            "de serapilheira. O Tier 1 só exige este valor em conversões de/para Forest Land."
        ),
    )

# Ausência validada: Tabela 2.2, coluna de madeira morta, e texto do Cap.2.
add(
    factor_id="DEADWOOD_C_NO_IPCC_DEFAULT",
    category="deadwood_carbon_stock",
    value=None,
    unit="tC/ha",
    pool="deadwood",
    tier=1,
    data_level="ipcc_default",
    validation_status="no_default_available",
    validated_by=VALIDATED_BY,
    validated_at=VALIDATED_AT,
    reference_id="IPCC2006_V4_CH2",
    page_or_table="Tabela 2.2 (coluna 'Dead wood carbon stocks', toda 'n.a.') e Seção 2.3.2.2",
    notes=(
        "AUSÊNCIA VALIDADA. O IPCC declara: 'it is currently not feasible to provide estimates of "
        "regional defaults values for ... dead wood carbon stocks', porque as compilações "
        "existentes não são amostras estatisticamente representativas. Madeira morta só entra por "
        "medição direta."
    ),
)

# ---------------------------------------------------------------------------
# SOLOS ORGÂNICOS DRENADOS — IPCC 2006 Vol.4 Cap.5, Tabela 5.6
# ---------------------------------------------------------------------------
for fid, temp, value in [
    ("EF_ORGANIC_SOIL_BOREAL_COOL_TEMPERATE", "boreal_cool_temperate", 5.0),
    ("EF_ORGANIC_SOIL_WARM_TEMPERATE", "warm_temperate", 10.0),
    ("EF_ORGANIC_SOIL_TROPICAL", "tropical_subtropical", 20.0),
]:
    validated(
        factor_id=fid,
        category="organic_soil_emission_factor",
        value=value,
        unit="tC/ha/ano",
        gas="CO2",
        pool="soil_organic_carbon",
        temperature_regime=temp,
        land_use=["cropland", "agroforestry"],
        tier=1,
        data_level="ipcc_default",
        uncertainty_percent=90.0,
        methodology="IPCC 2006 Tier 1",
        reference_id="IPCC2006_V4_CH5",
        page_or_table="Tabela 5.6",
        notes="Perda anual de C por drenagem de solo orgânico (Histossolo). Aplica-se apenas a solo orgânico DRENADO.",
    )

# ---------------------------------------------------------------------------
# EMISSÕES OPERACIONAIS — BRASIL
# ---------------------------------------------------------------------------
validated(
    factor_id="EF_ELECTRICITY_SIN_BR_2023",
    category="operational_emission_factor",
    value=0.0385,
    unit="tCO2/MWh",
    gas="CO2",
    country="Brazil",
    year=2023,
    level="electricity",
    factor_kind="fator_medio_anual",
    tier=1,
    data_level="national",
    methodology="MCTI/SIRENE — fator médio anual do SIN para inventários corporativos",
    reference_id="MCTI_SIRENE_FE_ELETRICIDADE",
    page_or_table="Comunicado oficial MCTI sobre o fator de 2023",
    notes=(
        "APENAS CO2 — não inclui CH4 nem N2O, portanto não é tCO2e completo. Fator MÉDIO "
        "(inventários), distinto da MARGEM DE OPERAÇÃO (MDL). Varia fortemente por ano: o "
        "comunicado registra 0,0292 em 2011 e valores acima de 1,0 em 2014, 2015 e 2021 "
        "(crises hídricas). Nunca extrapolar para outro ano."
    ),
)
for fid, level, desc in [
    ("EF_DIESEL_COMBUSTION_BR", "diesel", "Combustão de diesel em maquinário agrícola"),
    ("EF_GASOLINE_COMBUSTION_BR", "gasoline", "Combustão de gasolina"),
]:
    add(
        factor_id=fid,
        level=level,
        category="operational_emission_factor",
        value=None,
        unit="tCO2e/L",
        gas="multiple",
        country="Brazil",
        tier=1,
        data_level="national",
        validation_status="REQUIRES_VALIDATION",
        reference_id=None,
        page_or_table=None,
        notes=(
            f"{desc}. NÃO PESQUISADO nesta rodada. Exige IPCC 2006 Vol.2 (Energy) Cap.3 para os "
            "fatores por gás (CO2, CH4, N2O) + poder calorífico do combustível brasileiro (ANP/EPE) "
            "+ GWP declarado. Deve ser cadastrado como três fatores por gás, não como um tCO2e."
        ),
    )
add(
    factor_id="EF1_N2O_DIRECT_SYNTHETIC_N",
    level="fertilizer",
    category="operational_emission_factor",
    value=None,
    unit="kg N2O-N / kg N aplicado",
    gas="N2O",
    tier=1,
    data_level="ipcc_default",
    validation_status="REQUIRES_VALIDATION",
    reference_id=None,
    page_or_table=None,
    notes=(
        "EF1 do IPCC 2006 Vol.4 Cap.11, revisado pelo Refinamento 2019 (que desagrega por tipo de "
        "fertilizante e regime hídrico). NÃO PESQUISADO nesta rodada. A cadeia N -> N2O-N -> N2O "
        "(x 44/28) -> CO2e (x GWP) está implementada em core/n2o_engine.py e opera assim que "
        "este fator for preenchido."
    ),
)

# ---------------------------------------------------------------------------
payload = {
    "factor_database_version": VERSION,
    "built_by": "scripts/build_factor_database.py",
    "built_at": VALIDATED_AT,
    "factors": factors,
}
OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"{len(factors)} fatores gravados em {OUT}")
by_status: dict[str, int] = {}
for f in factors:
    by_status[f["validation_status"]] = by_status.get(f["validation_status"], 0) + 1
for k, v in sorted(by_status.items()):
    print(f"  {k}: {v}")
