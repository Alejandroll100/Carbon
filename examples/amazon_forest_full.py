"""Floresta natural amazônica — caminho totalmente validado, sem proxy.

Todos os fatores vêm da Tabela 4.4 (Updated) e 4.7 (Updated) do Refinamento
de 2019 e da Tabela 2.3 de 2006. Roda em modo científico estrito.
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from carbon.core.carbon_engine import CarbonEngine, CarbonEngineConfig
from carbon.models.enums import CalculationMode, IPCCClimateRegion, IPCCSoilType, LandUse
from carbon.models.inventory import CarbonInventory
from carbon.models.project import CarbonProject, Coordinates

project = CarbonProject(
    project_id="amz-primaria",
    name="Floresta primária — Amazônia",
    country="Brazil", state="Pará", land_use=LandUse.NATURAL_FOREST, area_ha=1000.0,
    coordinates=Coordinates(lat=-3.1, lon=-54.9), reference_year=2026,
    climate_region=IPCCClimateRegion.TROPICAL_WET, soil_type=IPCCSoilType.LAC,
    continent="North and South America", ecological_zone="tropical_rainforest",
    forest_origin="natural", forest_status="primary",
)
inventory = CarbonInventory(
    inventory_id="amz-2026", project_id=project.project_id, year=2026,
    mode=CalculationMode.QUICK_ESTIMATE,
)
result = CarbonEngine(config=CarbonEngineConfig(strict_factor_validation=True)).calculate(
    project, inventory
)

print("=" * 74)
print("FLORESTA PRIMÁRIA AMAZÔNICA — 1 000 ha — MODO CIENTÍFICO ESTRITO")
print("=" * 74)
for entry in result.audit.factors_used:
    print(f"  {entry['factor_id']}")
    print(f"      {entry['value']} {entry['unit']} · {entry['reference_id']} · {entry['page_or_table']}")
print()
stock = result.carbon_stock
for name, pool in stock.pools.items():
    c = pool.carbon_t
    if c.available:
        unc = f"±{c.uncertainty_percent:.1f}%" if c.uncertainty_percent is not None else "—"
        print(f"  {name:22s} {c.value:12,.1f} tC  {unc:>10s}  ({c.carbon_t_ha if hasattr(c,'carbon_t_ha') else pool.carbon_t_ha:,.1f} tC/ha)")
    else:
        print(f"  {name:22s} {'NOT AVAILABLE':>12s}")
print(f"\n  TOTAL              {stock.total_carbon_t:,.1f} tC  =  {stock.total_co2e_t:,.1f} tCO2e")
print(f"  por hectare        {stock.carbon_t_ha:,.1f} tC/ha")
print(f"  incerteza          " + (f"±{stock.uncertainty.uncertainty_percent:.1f}%"
      if stock.uncertainty.available else f"não reportada — {stock.uncertainty.reason}"))
print(f"  proxy usado        {result.proxy_used}")
print(f"  modo estrito       {result.audit.strict_factor_validation}")
print(f"  confiança          {result.quality.confidence_score}/100 ({result.quality.confidence_class.value})")
print(f"  lacunas            {', '.join(result.missing_data)}")
