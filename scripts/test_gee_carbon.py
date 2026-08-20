"""Teste de conexão com o Earth Engine e sondagem de cobertura real.

    py -m scripts.test_gee_carbon
    py -m scripts.test_gee_carbon --lat -24.497 --lon -47.844 --area-ha 100

Fora do CI: exige sessão autenticada. Serve para responder três perguntas
antes de qualquer análise:

1. a sessão inicializa?
2. os datasets declarados respondem?
3. esta AOI tem suporte amostral GEDI, ou não tem?

Nenhuma resposta é presumida. Se o GEE disser que não há footprint, o script
imprime que não há footprint.
"""

from __future__ import annotations

import argparse
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
from carbon.services.gee_cache import GEEQueryCache  # noqa: E402
from carbon.services.gee_client import GEEQueryError, RealEarthEngineClient  # noqa: E402
from carbon.services.gee_datasets import (  # noqa: E402
    ALL_DATASETS,
    gedi_covers_latitude,
    gedi_covers_year,
)
from carbon.services.gee_provider import (  # noqa: E402
    GoogleEarthEngineCarbonProvider,
    observation_window,
)
from carbon.services.geometry_service import aoi_from_point  # noqa: E402

#: Sondas de referência: floresta, agricultura e uma latitude fora do GEDI.
DEFAULT_PROBES = [
    ("Vale do Ribeira / SP (SAF-floresta)", -24.497, -47.844, 100.0, 2024),
    ("Amazônia / Novo Progresso PA (floresta)", -7.150, -55.400, 100.0, 2024),
    ("Sorriso / MT (agrícola)", -12.545, -55.711, 100.0, 2024),
    ("Norte da Finlândia (fora da cobertura GEDI)", 66.500, 25.700, 100.0, 2024),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Teste de conexão GEE — GEØ.IA Carbon")
    parser.add_argument("--lat", type=float, default=None)
    parser.add_argument("--lon", type=float, default=None)
    parser.add_argument("--area-ha", type=float, default=100.0)
    parser.add_argument("--year", type=int, default=2024)
    return parser.parse_args()


def probe(provider: GoogleEarthEngineCarbonProvider, label, lat, lon, area_ha, year) -> None:
    print(f"\n--- {label}")
    print(f"    lat={lat} lon={lon} area={area_ha} ha ano={year}")
    print(f"    cobertura latitudinal GEDI: {gedi_covers_latitude(lat)}")
    print(f"    cobertura temporal GEDI: {gedi_covers_year(year)}")
    start, end = observation_window(year)
    print(f"    janela solicitada: {start} .. {end}")

    aoi = aoi_from_point(lat, lon, area_ha)
    biomass = provider.observe_biomass(aoi, year)
    print(f"    GEDI status: {biomass.coverage_status.value} | suporte: {biomass.support.value}")
    print(f"    footprints: {biomass.sample_count}")
    if biomass.available:
        print(f"    AGBD média: {biomass.mean_agbd_mg_ha:.2f} Mg/ha")
        print(f"    biomassa seca total: {biomass.agb_total_t:.2f} t")
        print(
            "    incerteza amostral: "
            + (
                f"{biomass.sampling_uncertainty_percent:.2f} %"
                if biomass.uncertainty_available
                else "not_available"
            )
        )
    else:
        print(f"    motivo: {biomass.reason}")

    land_cover = provider.observe_land_cover(aoi, year)
    print(
        f"    cobertura dominante: "
        f"{land_cover.dominant_land_cover if land_cover.available else 'not_available'}"
    )
    indices = provider.observe_vegetation_indices(aoi, year)
    if indices.available:
        print(f"    NDVI: {indices.ndvi:.4f} | NDMI: {indices.ndmi:.4f}")
    else:
        print(f"    Sentinel-2: {indices.reason}")


def main() -> int:
    args = parse_args()
    config = GEEConfig.from_env()

    print("GEØ.IA CARBON — TESTE DE CONEXÃO GEE")
    print("=" * 60)
    for key, value in config.public_summary().items():
        print(f"{key}: {value}")

    try:
        client = RealEarthEngineClient(config)
    except EarthEngineDisabledError as exc:
        print(f"\nDESLIGADO: {exc}")
        return 2
    except EarthEngineNotInstalledError as exc:
        print(f"\nDEPENDÊNCIA AUSENTE: {exc}")
        return 3
    except EarthEngineAuthenticationError as exc:
        print(f"\nNÃO AUTENTICADO:\n{exc}")
        return 4

    print("\nSessão inicializada.")
    print("\nDatasets declarados:")
    for dataset in ALL_DATASETS:
        print(
            f"  {dataset.dataset_id} | {dataset.units or '-'} | "
            f"{dataset.spatial_resolution_m} m | "
            f"{dataset.temporal_start}..{dataset.temporal_end}"
        )

    provider = GoogleEarthEngineCarbonProvider(
        client, cache=GEEQueryCache(ttl_seconds=config.cache_ttl_seconds)
    )

    probes = (
        [("AOI informada", args.lat, args.lon, args.area_ha, args.year)]
        if args.lat is not None and args.lon is not None
        else DEFAULT_PROBES
    )
    failures = 0
    for label, lat, lon, area_ha, year in probes:
        try:
            probe(provider, label, lat, lon, area_ha, year)
        except GEEQueryError as exc:
            failures += 1
            print(f"    FALHA: {exc}")

    print("\n" + "=" * 60)
    print(f"Sondas executadas: {len(probes)} | falhas de consulta: {failures}")
    print("Ausência de footprint NÃO é falha: é resultado científico negativo.")
    return 0 if failures == 0 else 5


if __name__ == "__main__":
    raise SystemExit(main())
