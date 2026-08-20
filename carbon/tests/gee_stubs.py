"""Stub do Earth Engine para a suíte científica.

O GEE real NUNCA é necessário para rodar os testes. Este stub implementa o
mesmo contrato de ``EarthEngineClient`` devolvendo dicionários de números
crus — exatamente o que a redução server-side devolveria.
"""

from __future__ import annotations

from typing import Optional

from carbon.services.gee_client import GEEQueryError


def gedi_payload(
    *,
    sample_count: int = 40,
    mean: Optional[float] = 120.0,
    median: Optional[float] = 118.0,
    std: Optional[float] = 30.0,
    minimum: Optional[float] = 60.0,
    maximum: Optional[float] = 210.0,
    prediction_se: Optional[float] = 22.5,
    scene_count: int = 9,
    start: Optional[str] = "2024-02-01",
    end: Optional[str] = "2024-11-01",
) -> dict:
    return {
        "sample_count": sample_count,
        "mean_agbd_mg_ha": mean,
        "median_agbd_mg_ha": median,
        "std_agbd_mg_ha": std,
        "min_agbd_mg_ha": minimum,
        "max_agbd_mg_ha": maximum,
        "mean_prediction_se_mg_ha": prediction_se,
        "scene_count": scene_count,
        "observation_start": start,
        "observation_end": end,
        "scale_m": 25.0,
        "reducer": "stub",
    }


def canopy_payload(*, sample_count: int = 31, mean: float = 18.4) -> dict:
    return {
        "metric": "rh98",
        "sample_count": sample_count,
        "mean_canopy_height_m": mean,
        "median_canopy_height_m": mean,
        "std_canopy_height_m": 4.2,
        "scene_count": 7,
        "observation_start": "2024-02-01",
        "observation_end": "2024-11-01",
        "scale_m": 25.0,
        "reducer": "stub",
    }


def sentinel_payload(
    *,
    ndvi: Optional[float] = 0.78,
    evi: Optional[float] = 0.52,
    nbr: Optional[float] = 0.61,
    ndmi: Optional[float] = 0.34,
    scene_count: int = 44,
    valid_fraction: Optional[float] = 0.92,
    clear_score: Optional[float] = 0.81,
) -> dict:
    return {
        "ndvi": ndvi,
        "evi": evi,
        "nbr": nbr,
        "ndmi": ndmi,
        "valid_fraction": valid_fraction,
        "mean_clear_score": clear_score,
        "mean_scene_cloudy_percent": 18.0,
        "scene_count": scene_count,
        "observation_start": "2024-01-05",
        "observation_end": "2024-12-28",
        "scale_m": 20.0,
        "reducer": "stub",
        "evi_validation_status": "REQUIRES_VALIDATION",
    }


def land_cover_payload(
    *, counts: Optional[dict] = None, tree_probability: Optional[float] = 0.74
) -> dict:
    return {
        "class_pixel_counts": counts
        if counts is not None
        else {"trees": 7000.0, "crops": 2000.0, "grass": 1000.0},
        "tree_probability_mean": tree_probability,
        "scene_count": 44,
        "observation_start": "2024-01-05",
        "observation_end": "2024-12-28",
        "scale_m": 10.0,
        "reducer": "stub",
    }


class StubEarthEngineClient:
    """Cliente determinístico e contável, sem nenhuma dependência de rede."""

    def __init__(
        self,
        *,
        gedi: Optional[dict] = None,
        gedi_by_year: Optional[dict] = None,
        canopy: Optional[dict] = None,
        sentinel: Optional[dict] = None,
        land_cover: Optional[dict] = None,
        geodesic_area_ha_value: Optional[float] = None,
        fail: Optional[set] = None,
    ) -> None:
        self.gedi = gedi if gedi is not None else gedi_payload()
        self.gedi_by_year = gedi_by_year or {}
        self.canopy = canopy if canopy is not None else canopy_payload()
        self.sentinel = sentinel if sentinel is not None else sentinel_payload()
        self.land_cover = land_cover if land_cover is not None else land_cover_payload()
        self.geodesic_area_ha_value = geodesic_area_ha_value
        self.fail = fail or set()
        self.calls: list[tuple] = []

    def _record(self, name: str, start: str, end: str) -> None:
        self.calls.append((name, start, end))

    def call_count(self, name: str) -> int:
        return len([c for c in self.calls if c[0] == name])

    def geodesic_area_ha(self, geojson: dict) -> float:
        if "geometry" in self.fail:
            raise GEEQueryError("geometry", "stub configurado para falhar")
        if self.geodesic_area_ha_value is None:
            raise NotImplementedError("stub sem área geodésica configurada")
        return self.geodesic_area_ha_value

    def gedi_biomass_stats(self, geojson: dict, start: str, end: str) -> dict:
        self._record("gedi", start, end)
        if "gedi" in self.fail:
            raise GEEQueryError("LARSE/GEDI/GEDI04_A_002_MONTHLY", "stub: falha simulada")
        year = int(start[:4])
        return dict(self.gedi_by_year.get(year, self.gedi))

    def gedi_canopy_stats(self, geojson: dict, start: str, end: str) -> dict:
        self._record("canopy", start, end)
        if "canopy" in self.fail:
            raise GEEQueryError("LARSE/GEDI/GEDI02_A_002_MONTHLY", "stub: falha simulada")
        return dict(self.canopy)

    def sentinel2_indices(self, geojson: dict, start: str, end: str) -> dict:
        self._record("sentinel", start, end)
        if "sentinel" in self.fail:
            raise GEEQueryError("COPERNICUS/S2_SR_HARMONIZED", "stub: falha simulada")
        return dict(self.sentinel)

    def dynamic_world_land_cover(self, geojson: dict, start: str, end: str) -> dict:
        self._record("land_cover", start, end)
        if "land_cover" in self.fail:
            raise GEEQueryError("GOOGLE/DYNAMICWORLD/V1", "stub: falha simulada")
        return dict(self.land_cover)

    def esa_worldcover(self, geojson: dict) -> dict:
        self._record("worldcover", "-", "-")
        return {"class_pixel_counts": {"tree_cover": 9000.0}, "reference_year": "2021-01-01"}
