"""Cliente do Earth Engine — ÚNICA camada do módulo que importa ``ee``.

Fronteira deliberada: este arquivo faz consulta e redução server-side e
devolve `dict` de números crus. Nenhuma decisão científica acontece aqui —
limiar de suporte amostral, propagação de incerteza, escolha de estimador e
proveniência ficam em ``gee_provider.py``, que é testável sem internet.

Toda redução é server-side (``reduceRegion``): nenhum raster é trazido para o
Python. ``maxPixels`` e ``tileScale`` são configuráveis para AOIs grandes.
"""

from __future__ import annotations

import concurrent.futures
from typing import Any, Optional, Protocol

from ..config.gee import GEEConfig, initialize_earth_engine
from .gee_datasets import (
    CLOUD_SCORE_PLUS,
    DYNAMIC_WORLD,
    DYNAMIC_WORLD_CLASSES,
    ESA_WORLDCOVER,
    GEDI_L2A,
    GEDI_L4A,
    SENTINEL2_REFLECTANCE_SCALE,
    SENTINEL2_SR,
)

#: Escala de redução do GEDI: o próprio tamanho do footprint rasterizado.
GEDI_REDUCTION_SCALE_M = 25.0
#: Escala de redução dos índices Sentinel-2. O par SWIR (B11/B12) é de 20 m;
#: usar 20 m em todos os índices mantém NDVI, NDMI e NBR comparáveis entre si.
SENTINEL2_REDUCTION_SCALE_M = 20.0
#: Escala de redução dos produtos de cobertura da terra (10 m nativos).
LAND_COVER_REDUCTION_SCALE_M = 10.0
#: Limiar de pixel claro do Cloud Score+. O catálogo indica que valores entre
#: 0.50 e 0.65 funcionam bem; 0.60 é o valor do exemplo oficial.
CLOUD_SCORE_CLEAR_THRESHOLD = 0.60

#: Coeficientes da formulação padrão do EVI (Huete et al., 2002).
#: ATENÇÃO: transcritos da formulação de uso corrente, NÃO conferidos no
#: artigo primário nesta sessão. O EVI é usado apenas como INDICADOR de
#: vegetação — nunca é convertido em biomassa ou carbono —, por isso a
#: pendência não contamina nenhum número de carbono. Ainda assim ela é
#: declarada e propagada como warning na proveniência.
EVI_COEFFICIENTS = {"G": 2.5, "C1": 6.0, "C2": 7.5, "L": 1.0}
EVI_VALIDATION_STATUS = "REQUIRES_VALIDATION"
EVI_VALIDATION_NOTE = (
    "Coeficientes do EVI (G=2.5, C1=6, C2=7.5, L=1) não conferidos no artigo "
    "primário (Huete et al., 2002). EVI é usado apenas como indicador espectral."
)

MILLISECONDS_DATE_FORMAT = "YYYY-MM-dd"


class GEEQueryError(RuntimeError):
    """Falha em uma consulta ao Earth Engine, com o dataset identificado."""

    def __init__(self, dataset_id: str, message: str) -> None:
        super().__init__(f"[{dataset_id}] {message}")
        self.dataset_id = dataset_id
        self.message = message


class GEETimeoutError(GEEQueryError):
    """Consulta excedeu ``GEE_TIMEOUT_SECONDS``."""


class EarthEngineClient(Protocol):
    """Contrato do cliente. Os testes injetam um stub que implementa isto."""

    def geodesic_area_ha(self, geojson: dict) -> float: ...

    def gedi_biomass_stats(self, geojson: dict, start: str, end: str) -> dict: ...

    def gedi_canopy_stats(self, geojson: dict, start: str, end: str) -> dict: ...

    def sentinel2_indices(self, geojson: dict, start: str, end: str) -> dict: ...

    def dynamic_world_land_cover(self, geojson: dict, start: str, end: str) -> dict: ...

    def esa_worldcover(self, geojson: dict) -> dict: ...


class RealEarthEngineClient:
    """Implementação real. Inicializa o ``ee`` na construção — falha cedo."""

    def __init__(self, config: Optional[GEEConfig] = None, ee_module: Any = None) -> None:
        self.config = config or GEEConfig.from_env()
        self._ee = ee_module if ee_module is not None else initialize_earth_engine(self.config)

    # -- infraestrutura --------------------------------------------------------

    def _call(self, dataset_id: str, computation) -> Any:
        """Executa ``computation().getInfo()`` com timeout e erro identificado."""
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(computation)
            try:
                return future.result(timeout=self.config.timeout_seconds)
            except concurrent.futures.TimeoutError as exc:
                raise GEETimeoutError(
                    dataset_id,
                    f"consulta excedeu {self.config.timeout_seconds}s "
                    "(GEE_TIMEOUT_SECONDS). Reduza a AOI ou a janela temporal.",
                ) from exc
            except Exception as exc:
                raise GEEQueryError(dataset_id, str(exc)) from exc

    def _geometry(self, geojson: dict):
        try:
            return self._ee.Geometry(geojson)
        except Exception as exc:
            raise GEEQueryError("geometry", f"geometria inválida para o Earth Engine: {exc}") from exc

    def _reduce_region(self, image, geometry, reducer, scale: float):
        return image.reduceRegion(
            reducer=reducer,
            geometry=geometry,
            scale=scale,
            maxPixels=self.config.max_pixels,
            tileScale=self.config.tile_scale,
            bestEffort=False,
        )

    def _collection_window(self, collection) -> dict:
        ee = self._ee
        size = collection.size()
        start = ee.Algorithms.If(
            size.gt(0),
            ee.Date(collection.aggregate_min("system:time_start")).format(
                MILLISECONDS_DATE_FORMAT
            ),
            None,
        )
        end = ee.Algorithms.If(
            size.gt(0),
            ee.Date(collection.aggregate_max("system:time_start")).format(
                MILLISECONDS_DATE_FORMAT
            ),
            None,
        )
        return ee.Dictionary({"scene_count": size, "start": start, "end": end})

    # -- geometria -------------------------------------------------------------

    def geodesic_area_ha(self, geojson: dict) -> float:
        from ..utils.units import M2_PER_HA

        geometry = self._geometry(geojson)
        area_m2 = self._call("geometry", lambda: geometry.area(maxError=1).getInfo())
        return float(area_m2) / M2_PER_HA

    # -- GEDI L4A: biomassa aérea ---------------------------------------------

    def gedi_biomass_stats(self, geojson: dict, start: str, end: str) -> dict:
        ee = self._ee
        geometry = self._geometry(geojson)
        dataset_id = GEDI_L4A.dataset_id

        def quality_mask(image):
            return image.updateMask(image.select("l4_quality_flag").eq(1)).updateMask(
                image.select("degrade_flag").eq(0)
            )

        collection = (
            ee.ImageCollection(dataset_id)
            .filterBounds(geometry)
            .filterDate(start, end)
            .map(quality_mask)
            .select(["agbd", "agbd_se"])
        )
        # O mosaico colapsa footprints repetidos na MESMA célula de 25 m em
        # meses diferentes: sample_count é, portanto, a contagem de células
        # distintas com footprint retido — estimativa CONSERVADORA.
        mosaic = collection.mosaic()
        reducer = (
            ee.Reducer.count()
            .combine(ee.Reducer.mean(), sharedInputs=True)
            .combine(ee.Reducer.stdDev(), sharedInputs=True)
            .combine(ee.Reducer.median(), sharedInputs=True)
            .combine(ee.Reducer.minMax(), sharedInputs=True)
        )
        stats = self._reduce_region(mosaic, geometry, reducer, GEDI_REDUCTION_SCALE_M)
        payload = ee.Dictionary({"stats": stats, "window": self._collection_window(collection)})
        raw = self._call(dataset_id, lambda: payload.getInfo())

        stats = raw.get("stats") or {}
        window = raw.get("window") or {}
        return {
            "sample_count": int(stats.get("agbd_count") or 0),
            "mean_agbd_mg_ha": stats.get("agbd_mean"),
            "median_agbd_mg_ha": stats.get("agbd_median"),
            "std_agbd_mg_ha": stats.get("agbd_stdDev"),
            "min_agbd_mg_ha": stats.get("agbd_min"),
            "max_agbd_mg_ha": stats.get("agbd_max"),
            "mean_prediction_se_mg_ha": stats.get("agbd_se_mean"),
            "scene_count": int(window.get("scene_count") or 0),
            "observation_start": window.get("start"),
            "observation_end": window.get("end"),
            "scale_m": GEDI_REDUCTION_SCALE_M,
            "reducer": "count+mean+stdDev+median+minMax sobre mosaico com máscara de qualidade",
        }

    # -- GEDI L2A: altura de dossel -------------------------------------------

    def gedi_canopy_stats(self, geojson: dict, start: str, end: str) -> dict:
        ee = self._ee
        geometry = self._geometry(geojson)
        dataset_id = GEDI_L2A.dataset_id
        metric = "rh98"

        def quality_mask(image):
            return image.updateMask(image.select("quality_flag").eq(1)).updateMask(
                image.select("degrade_flag").eq(0)
            )

        collection = (
            ee.ImageCollection(dataset_id)
            .filterBounds(geometry)
            .filterDate(start, end)
            .map(quality_mask)
            .select([metric])
        )
        reducer = (
            ee.Reducer.count()
            .combine(ee.Reducer.mean(), sharedInputs=True)
            .combine(ee.Reducer.stdDev(), sharedInputs=True)
            .combine(ee.Reducer.median(), sharedInputs=True)
        )
        stats = self._reduce_region(
            collection.mosaic(), geometry, reducer, GEDI_REDUCTION_SCALE_M
        )
        payload = ee.Dictionary({"stats": stats, "window": self._collection_window(collection)})
        raw = self._call(dataset_id, lambda: payload.getInfo())

        stats = raw.get("stats") or {}
        window = raw.get("window") or {}
        return {
            "metric": metric,
            "sample_count": int(stats.get(f"{metric}_count") or 0),
            "mean_canopy_height_m": stats.get(f"{metric}_mean"),
            "median_canopy_height_m": stats.get(f"{metric}_median"),
            "std_canopy_height_m": stats.get(f"{metric}_stdDev"),
            "scene_count": int(window.get("scene_count") or 0),
            "observation_start": window.get("start"),
            "observation_end": window.get("end"),
            "scale_m": GEDI_REDUCTION_SCALE_M,
            "reducer": "count+mean+stdDev+median sobre mosaico rh98 com máscara de qualidade",
        }

    # -- Sentinel-2: índices espectrais ---------------------------------------

    def sentinel2_indices(self, geojson: dict, start: str, end: str) -> dict:
        ee = self._ee
        geometry = self._geometry(geojson)
        dataset_id = SENTINEL2_SR.dataset_id
        qa_band = "cs"

        base = (
            ee.ImageCollection(dataset_id).filterBounds(geometry).filterDate(start, end)
        )
        cloud_score = (
            ee.ImageCollection(CLOUD_SCORE_PLUS.dataset_id)
            .filterBounds(geometry)
            .filterDate(start, end)
        )
        linked = base.linkCollection(cloud_score, [qa_band])

        def mask_clouds(image):
            return image.updateMask(image.select(qa_band).gte(CLOUD_SCORE_CLEAR_THRESHOLD))

        masked = linked.map(mask_clouds)
        composite = masked.median()
        reflectance = composite.select(["B2", "B4", "B8", "B11", "B12"]).multiply(
            SENTINEL2_REFLECTANCE_SCALE
        )

        ndvi = reflectance.normalizedDifference(["B8", "B4"]).rename("ndvi")
        ndmi = reflectance.normalizedDifference(["B8", "B11"]).rename("ndmi")
        nbr = reflectance.normalizedDifference(["B8", "B12"]).rename("nbr")
        evi = reflectance.expression(
            "G * (nir - red) / (nir + C1 * red - C2 * blue + L)",
            {
                "nir": reflectance.select("B8"),
                "red": reflectance.select("B4"),
                "blue": reflectance.select("B2"),
                "G": EVI_COEFFICIENTS["G"],
                "C1": EVI_COEFFICIENTS["C1"],
                "C2": EVI_COEFFICIENTS["C2"],
                "L": EVI_COEFFICIENTS["L"],
            },
        ).rename("evi")
        valid = composite.select("B8").mask().rename("valid_fraction")
        indices = ndvi.addBands([evi, nbr, ndmi, valid])

        stats = self._reduce_region(
            indices, geometry, ee.Reducer.mean(), SENTINEL2_REDUCTION_SCALE_M
        )
        clear_score = self._reduce_region(
            linked.select(qa_band).mean().rename("clear_score"),
            geometry,
            ee.Reducer.mean(),
            SENTINEL2_REDUCTION_SCALE_M,
        )
        payload = ee.Dictionary(
            {
                "stats": stats,
                "clear": clear_score,
                "window": self._collection_window(base),
                "cloudy_percent": ee.Algorithms.If(
                    base.size().gt(0), base.aggregate_mean("CLOUDY_PIXEL_PERCENTAGE"), None
                ),
            }
        )
        raw = self._call(dataset_id, lambda: payload.getInfo())

        stats = raw.get("stats") or {}
        window = raw.get("window") or {}
        valid_fraction = stats.get("valid_fraction")
        return {
            "ndvi": stats.get("ndvi"),
            "evi": stats.get("evi"),
            "nbr": stats.get("nbr"),
            "ndmi": stats.get("ndmi"),
            "valid_fraction": valid_fraction,
            "mean_clear_score": (raw.get("clear") or {}).get("clear_score"),
            "mean_scene_cloudy_percent": raw.get("cloudy_percent"),
            "scene_count": int(window.get("scene_count") or 0),
            "observation_start": window.get("start"),
            "observation_end": window.get("end"),
            "scale_m": SENTINEL2_REDUCTION_SCALE_M,
            "reducer": f"mediana mascarada por Cloud Score+ {qa_band} >= "
            f"{CLOUD_SCORE_CLEAR_THRESHOLD}, depois média espacial",
            "evi_validation_status": EVI_VALIDATION_STATUS,
        }

    # -- Dynamic World: cobertura da terra ------------------------------------

    def dynamic_world_land_cover(self, geojson: dict, start: str, end: str) -> dict:
        ee = self._ee
        geometry = self._geometry(geojson)
        dataset_id = DYNAMIC_WORLD.dataset_id

        collection = (
            ee.ImageCollection(dataset_id).filterBounds(geometry).filterDate(start, end)
        )
        mode_label = collection.select("label").reduce(ee.Reducer.mode()).rename("label")
        histogram = self._reduce_region(
            mode_label, geometry, ee.Reducer.frequencyHistogram(), LAND_COVER_REDUCTION_SCALE_M
        )
        tree_probability = self._reduce_region(
            collection.select("trees").mean().rename("trees"),
            geometry,
            ee.Reducer.mean(),
            LAND_COVER_REDUCTION_SCALE_M,
        )
        payload = ee.Dictionary(
            {
                "histogram": histogram,
                "trees": tree_probability,
                "window": self._collection_window(collection),
            }
        )
        raw = self._call(dataset_id, lambda: payload.getInfo())

        histogram = ((raw.get("histogram") or {}).get("label")) or {}
        window = raw.get("window") or {}
        counts = {}
        for key, value in histogram.items():
            index = int(float(key))
            name = (
                DYNAMIC_WORLD_CLASSES[index]
                if 0 <= index < len(DYNAMIC_WORLD_CLASSES)
                else f"class_{index}"
            )
            counts[name] = float(value)
        return {
            "class_pixel_counts": counts,
            "tree_probability_mean": (raw.get("trees") or {}).get("trees"),
            "scene_count": int(window.get("scene_count") or 0),
            "observation_start": window.get("start"),
            "observation_end": window.get("end"),
            "scale_m": LAND_COVER_REDUCTION_SCALE_M,
            "reducer": "moda da banda label + histograma de frequência",
        }

    # -- ESA WorldCover: referência estática ----------------------------------

    def esa_worldcover(self, geojson: dict) -> dict:
        ee = self._ee
        geometry = self._geometry(geojson)
        dataset_id = ESA_WORLDCOVER.dataset_id

        image = ee.ImageCollection(dataset_id).first().select("Map")
        histogram = self._reduce_region(
            image, geometry, ee.Reducer.frequencyHistogram(), LAND_COVER_REDUCTION_SCALE_M
        )
        raw = self._call(dataset_id, lambda: histogram.getInfo())
        counts = {}
        from .gee_datasets import ESA_WORLDCOVER_CLASSES

        for key, value in ((raw or {}).get("Map") or {}).items():
            code = int(float(key))
            counts[ESA_WORLDCOVER_CLASSES.get(code, f"class_{code}")] = float(value)
        return {
            "class_pixel_counts": counts,
            "reference_year": ESA_WORLDCOVER.temporal_start,
            "scale_m": LAND_COVER_REDUCTION_SCALE_M,
            "reducer": "histograma de frequência da banda Map",
        }
