"""Cenário completo: SAF brasileiro, do input à proveniência.

Nenhum número deste exemplo é inventado: todos vêm da base de fatores validada
ou do inventário de campo declarado abaixo.
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from carbon.core.carbon_engine import CarbonEngine, CarbonEngineConfig
from carbon.factors.soil_classification import to_ipcc_soil_type
from carbon.models.enums import (
    CalculationMode, IPCCClimateRegion, LandUse, OperationalEmissionSource,
)
from carbon.models.inventory import (
    BiomassObservation, CarbonInventory, OperationalEmissionEntry, SoilObservation,
)
from carbon.models.project import CarbonProject, Coordinates
from carbon.services.factor_service import ProxyAuthorization

BAR = "=" * 74

def h(title: str) -> None:
    print(f"\n{BAR}\n{title}\n{BAR}")

# --------------------------------------------------------------------- INPUT
soil = to_ipcc_soil_type("Latossolo")  # SiBCS -> IPCC
project = CarbonProject(
    project_id="saf-vale-ribeira",
    name="SAF Vale do Ribeira",
    country="Brazil", state="São Paulo", municipality="Registro",
    land_use=LandUse.AGROFORESTRY, area_ha=100.0,
    coordinates=Coordinates(lat=-24.4970, lon=-47.8440), reference_year=2026,
    climate_region=IPCCClimateRegion.TROPICAL_MOIST,
    soil_type=soil.ipcc_soil_type,
    soil_type_source_classification="SiBCS: Latossolo",
    region="South America", ecological_zone="humid_tropical_lowland",
)
baseline = CarbonInventory(
    inventory_id="saf-2021", project_id=project.project_id, year=2021,
    mode=CalculationMode.INVENTORY,
    aboveground=BiomassObservation(dry_biomass_t_ha=28.4, uncertainty_percent=18.0,
                                   source="parcelas permanentes 2021"),
    soil=SoilObservation(depth_cm=30.0, bulk_density_g_cm3=1.18,
                         organic_carbon_percent=1.92, sample_count=12,
                         uncertainty_percent=11.0, source="amostragem 2021"),
)
current = CarbonInventory(
    inventory_id="saf-2026", project_id=project.project_id, year=2026,
    mode=CalculationMode.INVENTORY,
    aboveground=BiomassObservation(dry_biomass_t_ha=61.7, uncertainty_percent=16.0,
                                   source="parcelas permanentes 2026"),
    soil=SoilObservation(depth_cm=30.0, bulk_density_g_cm3=1.15,
                         organic_carbon_percent=2.31, sample_count=12,
                         uncertainty_percent=10.0, source="amostragem 2026"),
)
emissions = [
    OperationalEmissionEntry(source=OperationalEmissionSource.ELECTRICITY,
                             activity_amount=42.0, activity_unit="MWh",
                             year=2023, country="Brazil"),
    OperationalEmissionEntry(source=OperationalEmissionSource.DIESEL,
                             activity_amount=3200.0, activity_unit="L"),
]

h("INPUT")
print(f"  {project.name} — {project.area_ha:g} ha, {project.municipality}/{project.state}")
print(f"  uso da terra:     {project.land_use.value}")
print(f"  região climática: {project.climate_region.value}")
print(f"  solo:             {project.soil_type_source_classification} -> "
      f"WRB {soil.wrb_equivalent} -> IPCC {soil.ipcc_soil_type.value}")
for w in soil.warnings:
    print(f"    aviso: {w}")
print(f"  inventários:      2021 (AGB 28,4 t m.s./ha) e 2026 (AGB 61,7 t m.s./ha)")

config = CarbonEngineConfig(
    root_to_shoot_proxy=ProxyAuthorization(
        factor_id="RS_TROPICAL_MOIST_AMERICAS_NATURAL_LE125",
        justification=("Não existe default IPCC de razão raiz:parte aérea para SAF "
                       "(Cap.5, Seção 5.2.1.2). Floresta tropical úmida natural da América "
                       "do Sul (Tabela 4.4 de 2019) adotada como classe análoga do estrato "
                       "arbóreo, sob responsabilidade técnica do projeto."),
    )
)
result = CarbonEngine(config=config).calculate(
    project, current, baseline_inventory=baseline, operational_emissions=emissions
)

h("FACTOR RESOLUTION")
for entry in result.audit.factors_used:
    tag = " [PROXY]" if entry["proxy"] else ""
    print(f"  {entry['factor_id']}{tag}")
    print(f"      {entry['value']} {entry['unit']}  ·  {entry['data_level']}  ·  "
          f"{entry['validation_status']}")
    print(f"      {entry['reference_id'] or entry['source_citation']} — "
          f"{entry['page_or_table'] or 'parâmetro do projeto'}")

stock = result.carbon_stock
h("BIOMASS")
for name in ("aboveground_biomass", "belowground_biomass"):
    pool = stock.pools[name]
    bm = pool.dry_biomass_t
    if bm and bm.available:
        print(f"  {name:22s} {bm.value:12,.1f} t m.s.  ({bm.estimation_type.value})")
    else:
        print(f"  {name:22s} {'indisponível':>12s}")
        print(f"      {(bm.notes[0] if bm and bm.notes else '')[:110]}")

h("CARBON POOLS")
for name, pool in stock.pools.items():
    c = pool.carbon_t
    if c.available:
        unc = f"±{c.uncertainty_percent:.1f}%" if c.uncertainty_percent is not None else "sem incerteza"
        print(f"  {name:22s} {c.value:12,.1f} tC   {unc:>16s}   {c.estimation_type.value}")
    else:
        print(f"  {name:22s} {'NOT AVAILABLE':>12s}")

h("TOTAL CARBON  ->  CO2e")
print(f"  pools disponíveis: {', '.join(stock.available_pools)}")
print(f"  pools ausentes:    {', '.join(stock.missing_pools) or 'nenhum'}")
print(f"  total              {stock.total_carbon_t:,.1f} tC  ({stock.status.value})")
print(f"  por hectare        {stock.carbon_t_ha:,.2f} tC/ha")
print(f"  CO2 equivalente    {stock.total_co2e_t:,.1f} tCO2e   (x 44/12, razão de massa molar)")

h("CHANGE  ->  REMOVAL")
ch = result.change
print(f"  período            {ch.baseline_year} -> {ch.current_year} ({ch.period_years} anos)")
print(f"  variação           {ch.delta_carbon_t:+,.1f} tC  ({ch.delta_co2e_t:+,.1f} tCO2e)")
print(f"  direção            {ch.direction}")
print(f"  pools comparados   {', '.join(ch.comparable_pools)}")
if ch.non_comparable_pools:
    print(f"  NÃO comparáveis    {', '.join(p.pool for p in ch.non_comparable_pools)}")
rm = result.removal
print(f"  remoção            {rm.annual_co2_removal_tCO2e_year:+,.1f} tCO2e/ano  "
      f"({rm.annual_co2_removal_tCO2e_ha_year:+,.2f} tCO2e/ha/ano)")

h("OPERATIONAL EMISSIONS  ->  NET BALANCE")
for e in result.operational_emissions.entries:
    if "emission_tCO2e" in e and e.get("emission_tCO2e") is not None:
        print(f"  {e['source']} ({e['year']}): {e['emission_tCO2e']:,.2f} tCO2e  "
              f"[{e['factor_id']}]")
        print(f"      {e['completeness']}")
    else:
        print(f"  {e['source']}: NÃO CALCULADO — {e['reason']}")
print(f"  total operacional  {result.operational_emissions.total_tCO2e:,.2f} tCO2e")
nb = result.net_balance
print(f"  remoções brutas    {nb.gross_removals_tCO2e:+,.1f} tCO2e")
print(f"  emissões oper.     {nb.operational_emissions_tCO2e:,.2f} tCO2e")
print(f"  balanço líquido    {nb.net_balance_tCO2e:+,.1f} tCO2e   ({nb.status})")
for c in nb.excluded_components:
    print(f"      excluído: {c}")
for n in nb.notes:
    print(f"      {n}")

h("UNCERTAINTY  ->  CONFIDENCE")
u = stock.uncertainty
if u.available:
    print(f"  incerteza do estoque   ±{u.uncertainty_percent:.1f}%")
    print(f"  intervalo              {u.lower_bound:,.1f} – {u.upper_bound:,.1f} tC")
    print(f"  método                 {u.method}")
else:
    print(f"  incerteza              NÃO REPORTADA — {u.reason}")
q = result.quality
print(f"  confidence score       {q.confidence_score}/100 ({q.confidence_class.value})")
print(f"  data quality score     {q.data_quality_score}/100")
for p in q.penalties:
    print(f"      penalidade: {p}")

h("PROVENANCE")
a = result.audit
print(f"  engine {a.engine_version} · fatores {a.factor_database_version} · "
      f"metodologia {a.methodology_version} · bibliografia {a.reference_database_version}")
print(f"  strict_factor_validation={a.strict_factor_validation}  "
      f"allow_scientific_proxy={a.allow_scientific_proxy}  proxy_used={result.proxy_used}")
print(f"  fingerprint {a.input_fingerprint[:16]}…")
print(f"  rastros de resolução: {len(a.resolution_traces)}")
print("\n  equações aplicadas:")
for eq in {e for p in stock.pools.values() for e in p.carbon_t.equations_used}:
    print(f"      {eq}")
print("\n  lacunas declaradas:")
for m in result.missing_data:
    print(f"      - {m}")
for uf in result.unresolved_factors:
    print(f"      - {uf['category']} ({uf['purpose']})")
if result.sanity_findings:
    print("\n  verificações de plausibilidade:")
    for f in result.sanity_findings:
        print(f"      [{f['severity']}] {f['code']}: {f['message'][:90]}")
print("\n  avisos:")
for w in result.validation_warnings:
    print(f"      - {w[:130]}")
