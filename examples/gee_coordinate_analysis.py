"""Análise geoespacial de carbono por coordenada, contra o Earth Engine REAL.

Uso:

    py -m examples.gee_coordinate_analysis --lat -24.497 --lon -47.844 --area-ha 100 --year 2024

Este script NÃO faz parte do CI: ele exige sessão autenticada do Earth Engine.
Nenhum valor é embutido no código — tudo que aparece na saída veio da consulta.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from carbon.config.gee import (  # noqa: E402
    EarthEngineAuthenticationError,
    EarthEngineDisabledError,
    EarthEngineNotInstalledError,
    GEEConfig,
)
from carbon.models.enums import LandUse  # noqa: E402
from carbon.services.gee_cache import GEEQueryCache  # noqa: E402
from carbon.services.gee_client import RealEarthEngineClient  # noqa: E402
from carbon.services.gee_provider import GoogleEarthEngineCarbonProvider  # noqa: E402
from carbon.services.geospatial_analysis import (  # noqa: E402
    GeospatialAnalysisInput,
    GeospatialCarbonService,
)

SEPARATOR = "=" * 68


def fmt(value, suffix: str = "", decimals: int = 2) -> str:
    """Formata sem inventar precisão: ausência aparece como 'not_available'."""
    if value is None:
        return "not_available"
    if isinstance(value, bool):
        return "sim" if value else "não"
    if isinstance(value, (int, float)):
        return f"{value:,.{decimals}f}{suffix}".replace(",", " ")
    return f"{value}{suffix}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="GEØ.IA Carbon — análise GEE por coordenada")
    parser.add_argument("--lat", type=float, required=True)
    parser.add_argument("--lon", type=float, required=True)
    parser.add_argument("--area-ha", type=float, default=100.0)
    parser.add_argument("--year", type=int, default=2024)
    parser.add_argument("--baseline-year", type=int, default=None)
    parser.add_argument(
        "--land-use",
        default=LandUse.AGROFORESTRY.value,
        choices=[item.value for item in LandUse],
    )
    parser.add_argument("--country", default="Brazil")
    parser.add_argument("--geojson", default=None, help="caminho de um arquivo GeoJSON")
    parser.add_argument("--window-months", type=int, default=0)
    parser.add_argument("--json-out", default=None, help="salva a resposta completa")
    return parser.parse_args()


def build_service() -> GeospatialCarbonService:
    config = GEEConfig.from_env()
    print("GEE authentication")
    for key, value in config.public_summary().items():
        print(f"  {key}: {value}")
    client = RealEarthEngineClient(config)
    print("  status: sessão inicializada")
    provider = GoogleEarthEngineCarbonProvider(
        client, cache=GEEQueryCache(ttl_seconds=config.cache_ttl_seconds)
    )
    return GeospatialCarbonService(provider)


def print_report(body: dict) -> None:
    geometry = body["geometry"]
    remote = body["remote_sensing"]
    biomass = remote["biomass"]
    canopy = remote["canopy"]
    land_cover = remote["land_cover"]
    indices = remote["vegetation_indices"]
    carbon = body["carbon"]
    stock = carbon.get("carbon_stock") or {}

    print()
    print("GEØ.IA CARBON — GEE ANALYSIS")
    print(SEPARATOR)

    print("\nAOI")
    print(f"  lat: {fmt(geometry['centroid']['lat'], decimals=6)}")
    print(f"  lon: {fmt(geometry['centroid']['lon'], decimals=6)}")
    print(f"  área: {fmt(geometry['geometry_area_ha'], ' ha', 4)}")
    print(f"  origem da geometria: {geometry['geometry_source']}")
    print(f"  origem da área: {geometry['area_source']}")
    print(f"  hash: {geometry['geometry_hash'][:16]}...")

    print("\nGEDI L4A (biomassa aérea)")
    print(f"  status: {biomass['coverage_status']}")
    print(f"  suporte amostral: {biomass['support']}")
    print(f"  footprints: {biomass['sample_count']}")
    print(f"  AGBD média: {fmt(biomass['mean_agbd_mg_ha'], ' Mg/ha')}")
    print(f"  AGBD mediana: {fmt(biomass['median_agbd_mg_ha'], ' Mg/ha')}")
    print(f"  AGBD desvio-padrão: {fmt(biomass['std_agbd_mg_ha'], ' Mg/ha')}")
    print(f"  erro de predição médio (agbd_se): {fmt(biomass['mean_prediction_se_mg_ha'], ' Mg/ha')}")
    print(f"  incerteza amostral: {fmt(biomass['sampling_uncertainty_percent'], ' %')}")
    print(f"  erro do modelo incluído: {fmt(biomass['model_error_included'])}")
    print(f"  biomassa seca total: {fmt(biomass['agb_total_t'], ' t d.m.')}")
    if biomass.get("window"):
        window = biomass["window"]
        print(f"  ano solicitado: {window['requested_year']}")
        print(
            f"  observação efetiva: {fmt(window['actual_observation_start'])} .. "
            f"{fmt(window['actual_observation_end'])} ({fmt(window['scene_count'])} cenas)"
        )
    if biomass.get("reason"):
        print(f"  motivo: {biomass['reason']}")

    print("\nSENTINEL-2")
    print(f"  status: {indices['coverage_status']}")
    print(f"  cenas: {fmt((indices.get('window') or {}).get('scene_count'), '', 0)}")
    print(f"  NDVI: {fmt(indices['ndvi'], '', 4)}")
    print(f"  EVI:  {fmt(indices['evi'], '', 4)}")
    print(f"  NBR:  {fmt(indices['nbr'], '', 4)}")
    print(f"  NDMI: {fmt(indices['ndmi'], '', 4)}")
    print(f"  fração mascarada por nuvem: {fmt(indices['cloud_masked_fraction'], '', 4)}")
    print("  (índices são contexto/QA/feature — nunca carbono)")

    print("\nCANOPY (GEDI L2A)")
    print(f"  status: {canopy['coverage_status']}")
    print(f"  métrica: {fmt(canopy['metric'])}")
    print(f"  altura média: {fmt(canopy['mean_canopy_height_m'], ' m')}")
    print(f"  footprints: {canopy['sample_count']}")

    print("\nLAND COVER (Dynamic World)")
    print(f"  dominante: {fmt(land_cover['dominant_land_cover'])}")
    for name, percent in sorted(
        (land_cover.get("land_cover_distribution_percent") or {}).items(),
        key=lambda item: -item[1],
    ):
        print(f"  {name}: {fmt(percent, ' %')}")
    consistency = remote["consistency"]
    print(f"  consistência com uso declarado: {fmt(consistency.get('consistent'))}")
    if consistency.get("message"):
        print(f"  {consistency['message']}")

    print("\nDECISÃO DE FONTE DE BIOMASSA")
    decision = remote["source_decision"]
    print(f"  selecionada: {decision['selected']}")
    print(f"  motivo: {decision['reason']}")
    for rejected in decision["rejected"]:
        print(f"  recusada [{rejected['level']}]: {rejected['reason']}")

    print("\nCARBON ENGINE")
    for name, pool in (stock.get("pools") or {}).items():
        value = pool["carbon_t"]["value"]
        print(f"  {name}: {fmt(value, ' tC')}")
    print(f"  total: {fmt(stock.get('total_carbon_t'), ' tC')}")
    print(f"  CO2e: {fmt(stock.get('total_co2e_t'), ' tCO2e')}")
    print(f"  intensidade: {fmt(stock.get('co2e_t_ha'), ' tCO2e/ha')}")
    change = carbon.get("change")
    if change:
        print(f"  ΔC ({change['baseline_year']}→{change['current_year']}): "
              f"{fmt(change.get('delta_carbon_t'), ' tC')}")
    removal = carbon.get("removal")
    if removal:
        print(f"  remoção: {fmt(removal.get('annual_co2_removal_tCO2e_year'), ' tCO2e/ano')}")

    print("\nQUALITY")
    uncertainty = (stock.get("uncertainty") or {})
    print(f"  incerteza do estoque: {fmt(uncertainty.get('uncertainty_percent'), ' %')}")
    if not uncertainty.get("available"):
        print(f"    motivo: {fmt(uncertainty.get('reason'))}")
    engine_quality = body["quality"]["engine_confidence"] or {}
    support = body["quality"]["remote_sensing_support"]
    print(f"  confidence (motor): {fmt(engine_quality.get('confidence_score'), '', 0)}")
    print(f"  data quality: {fmt(engine_quality.get('data_quality_score'), '', 0)}")
    print(
        f"  remote sensing support: "
        f"{fmt(support['remote_sensing_support_score'], '', 0)}"
    )

    print("\nWARNINGS")
    if not body["warnings"]:
        print("  (nenhum)")
    for warning in body["warnings"]:
        print(f"  - {warning}")

    print("\nPROVENANCE")
    for name, provenance in body["provenance"]["observations"].items():
        if not provenance:
            continue
        print(f"  {name}: {provenance['dataset_id']} | bandas={provenance['bands']} | "
              f"escala={fmt(provenance['scale_m'], ' m', 0)} | "
              f"n={fmt(provenance['sample_count'], '', 0)} | "
              f"cache_hit={fmt(provenance['cache_hit'])}")
        for filtro in provenance["quality_filters"]:
            print(f"      filtro: {filtro}")

    print()
    print(SEPARATOR)
    print(body["disclaimer"])


def main() -> int:
    args = parse_args()
    geometry = None
    if args.geojson:
        geometry = json.loads(Path(args.geojson).read_text(encoding="utf-8"))

    try:
        service = build_service()
    except (
        EarthEngineDisabledError,
        EarthEngineNotInstalledError,
        EarthEngineAuthenticationError,
    ) as exc:
        print(f"\nERRO: {exc}")
        return 2

    request = GeospatialAnalysisInput(
        lat=args.lat,
        lon=args.lon,
        area_ha=args.area_ha,
        geometry=geometry,
        current_year=args.year,
        baseline_year=args.baseline_year,
        land_use=LandUse(args.land_use),
        country=args.country,
        window_expansion_months=args.window_months,
    )
    body = service.analyze(request)
    print_report(body)

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(body, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"\nResposta completa salva em {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
