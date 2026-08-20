"""Provider de sensoriamento remoto sobre o Google Earth Engine.

Este arquivo contém as DECISÕES CIENTÍFICAS da camada geoespacial e nenhuma
chamada ao SDK ``ee`` — o acesso fica em ``gee_client.py``. Por isso tudo
aqui é testável sem internet e sem credencial.

Invariantes que o código impõe:

* GEDI L4A entrega BIOMASSA AÉREA SECA (Mg/ha). O provider converte densidade
  em total (x área) e para por aí: a fração de carbono é aplicada uma única
  vez, pelo Carbon Engine.
* ausência de footprint NÃO é zero — é ``coverage_status`` com motivo;
* incerteza nunca é fabricada: só é reportada a componente AMOSTRAL, que é
  calculável a partir da dispersão observada. O erro de predição do modelo
  GEDI é preservado em bruto e declarado como NÃO incluído;
* índice espectral não é convertido em carbono em nenhum caminho de código.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Optional

from ..models.enums import DataLevel, EstimationType, LandUse
from ..models.provenance import TracedValue
from ..models.remote_sensing import (
    AreaOfInterest,
    BiomassRemoteObservation,
    CanopyRemoteObservation,
    CoverageStatus,
    LandCoverConsistency,
    LandCoverObservation,
    ObservationWindow,
    ObservedLandChange,
    RemoteSensingBundle,
    RemoteSensingProvenance,
    SamplingSupport,
    VegetationIndicators,
)
from .gee_cache import GEEQueryCache, cache_key
from .gee_client import EarthEngineClient, GEEQueryError
from .gee_datasets import (
    DYNAMIC_WORLD,
    GEDI_FOOTPRINT_DIAMETER_M,
    GEDI_L2A,
    GEDI_L4A,
    SENTINEL2_SR,
    gedi_covers_latitude,
    gedi_covers_year,
)
from .geospatial_service import vegetation_index_role
from .inventory_service import Z_SCORE_95
from ..utils.units import M2_PER_HA

DRY_MATTER_UNIT = "t dry matter"

#: Limiares de SUPORTE AMOSTRAL do GEDI.
#:
#: São limiares OPERACIONAIS GEØ.IA, não valores de literatura nem fatores
#: IPCC. Justificativa: (a) com 0 footprints não existe observação; (b) com
#: menos de 2 a dispersão não é estimável e nenhuma incerteza amostral pode
#: ser calculada — a mesma regra que o motor já aplica a parcelas de campo;
#: (c) abaixo de 20 unidades amostrais o erro padrão da média fica dominado
#: pelo próprio tamanho da amostra. Quem discordar dos cortes pode alterá-los
#: aqui: eles são dado declarado, não regra escondida em ``if``.
SAMPLING_SUPPORT_RATIONALE = (
    "Limiares operacionais GEØ.IA: 0 = sem observação; 1-4 = suporte muito baixo "
    "(sem dispersão confiável); 5-19 = suporte baixo; >=20 = utilizável. Não são "
    "valores IPCC nem de literatura."
)
VERY_LOW_SUPPORT_MAX_FOOTPRINTS = 4
LOW_SUPPORT_MAX_FOOTPRINTS = 19
USABLE_SUPPORT_MIN_FOOTPRINTS = 20
#: Abaixo disso não há variância amostral: incerteza não é reportada.
MIN_FOOTPRINTS_FOR_SAMPLING_UNCERTAINTY = 2

#: Área nominal de um footprint GEDI, derivada do diâmetro declarado.
GEDI_FOOTPRINT_AREA_M2 = math.pi * (GEDI_FOOTPRINT_DIAMETER_M / 2.0) ** 2

SAMPLING_UNCERTAINTY_METHOD = (
    "erro padrão entre footprints x 1.96 (apenas amostragem; sem erro do modelo GEDI)"
)

#: Classe dominante acima desta fração da AOI define ``dominant_land_cover``.
DOMINANCE_THRESHOLD_PERCENT = 50.0

#: Cobertura observada compatível com cada uso da terra declarado.
LAND_USE_EXPECTED_COVER: dict[str, set] = {
    LandUse.NATURAL_FOREST.value: {"trees"},
    LandUse.SECONDARY_FOREST.value: {"trees", "shrub_and_scrub"},
    LandUse.PLANTED_FOREST.value: {"trees"},
    LandUse.REFORESTATION.value: {"trees", "shrub_and_scrub", "grass"},
    LandUse.FOREST_RESTORATION.value: {"trees", "shrub_and_scrub", "grass"},
    LandUse.AGROFORESTRY.value: {"trees", "crops", "grass", "shrub_and_scrub"},
    LandUse.SILVOPASTORAL.value: {"trees", "grass", "shrub_and_scrub"},
    LandUse.CROPLAND.value: {"crops", "grass", "bare"},
    LandUse.PASTURE.value: {"grass", "crops", "shrub_and_scrub"},
    LandUse.DEGRADED_LAND.value: {"bare", "grass", "shrub_and_scrub"},
}
#: Cobertura que torna o uso declarado insustentável: não se calcula estoque
#: de biomassa de uma AOI dominada por água, área construída ou neve.
BLOCKING_COVER_CLASSES = {"water", "built", "snow_and_ice"}


def mg_ha_to_t_ha(value_mg_ha: float) -> float:
    """1 Mg = 1 tonelada métrica. Identidade de unidade, explicitada."""
    return value_mg_ha


def total_dry_biomass_t(density_t_ha: float, area_ha: float) -> float:
    """Aplicação espacial de uma densidade EXPLÍCITA de biomassa.

    NÃO é conversão de índice espectral: a entrada já é biomassa por hectare.
    A fração de carbono não é aplicada aqui.
    """
    return density_t_ha * area_ha


def classify_sampling_support(sample_count: int) -> SamplingSupport:
    if sample_count <= 0:
        return SamplingSupport.UNAVAILABLE
    if sample_count <= VERY_LOW_SUPPORT_MAX_FOOTPRINTS:
        return SamplingSupport.VERY_LOW_SUPPORT
    if sample_count <= LOW_SUPPORT_MAX_FOOTPRINTS:
        return SamplingSupport.LOW_SUPPORT
    return SamplingSupport.USABLE


def sampling_uncertainty_percent(
    mean: Optional[float], std: Optional[float], sample_count: int
) -> Optional[float]:
    """Meia-largura do IC 95% da MÉDIA, em % — só a componente amostral.

    Mesma convenção já usada no inventário de parcelas do motor. Devolve
    ``None`` (e não um número plausível) quando não é calculável.
    """
    if mean is None or std is None:
        return None
    if sample_count < MIN_FOOTPRINTS_FOR_SAMPLING_UNCERTAINTY or mean <= 0:
        return None
    standard_error = std / math.sqrt(sample_count)
    return Z_SCORE_95 * standard_error / mean * 100


def observation_window(
    year: int, *, expansion_months: int = 0
) -> tuple[str, str]:
    """Janela temporal solicitada. Default: ano civil inteiro.

    ``expansion_months`` alarga a janela dos dois lados (ex.: 6 -> ±6 meses).
    """
    start_year = year
    start_month = 1 - expansion_months
    while start_month <= 0:
        start_month += 12
        start_year -= 1
    end_year = year + 1
    end_month = 1 + expansion_months
    while end_month > 12:
        end_month -= 12
        end_year += 1
    return (
        f"{start_year:04d}-{start_month:02d}-01",
        f"{end_year:04d}-{end_month:02d}-01",
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class GoogleEarthEngineCarbonProvider:
    """Implementa ``RemoteSensingCarbonProvider`` sobre datasets reais do GEE."""

    name = "google_earth_engine"

    def __init__(
        self,
        client: EarthEngineClient,
        *,
        cache: Optional[GEEQueryCache] = None,
        window_expansion_months: int = 0,
    ) -> None:
        self.client = client
        self.cache = cache or GEEQueryCache(ttl_seconds=0)
        self.window_expansion_months = window_expansion_months

    # -- infraestrutura --------------------------------------------------------

    def _cached(self, dataset_id: str, aoi: AreaOfInterest, start: str, end: str, fetch):
        key = cache_key(dataset_id, aoi.geometry_hash, start, end)
        entry = self.cache.get(key)
        if entry is not None:
            return entry.value, True, entry.acquired_at
        value = fetch()
        acquired_at = _now()
        self.cache.set(key, dataset_id, value, acquired_at)
        return value, False, acquired_at

    def _provenance(
        self,
        descriptor,
        aoi: AreaOfInterest,
        window: ObservationWindow,
        raw: dict,
        *,
        bands: list,
        cache_hit: bool,
        retrieval_timestamp: str,
        sample_count: Optional[int] = None,
        data_level: Optional[DataLevel] = None,
        warnings: Optional[list] = None,
    ) -> RemoteSensingProvenance:
        fields = descriptor.provenance_fields()
        return RemoteSensingProvenance(
            provider=self.name,
            bands=bands,
            requested_year=window.requested_year,
            observation_start=window.actual_observation_start,
            observation_end=window.actual_observation_end,
            scene_count=window.scene_count,
            retrieval_timestamp=retrieval_timestamp,
            geometry_hash=aoi.geometry_hash,
            geometry_source=aoi.geometry_source.value,
            area_ha=aoi.area_ha,
            scale_m=raw.get("scale_m"),
            reducer=raw.get("reducer"),
            sample_count=sample_count,
            quality_filters=list(descriptor.quality_filters),
            data_level=data_level,
            cache_hit=cache_hit,
            warnings=list(warnings or []),
            limitations=list(descriptor.limitations),
            **fields,
        )

    def _window(self, year: int, raw: dict) -> ObservationWindow:
        start, end = observation_window(year, expansion_months=self.window_expansion_months)
        return ObservationWindow(
            requested_year=year,
            requested_start=start,
            requested_end=end,
            actual_observation_start=raw.get("observation_start"),
            actual_observation_end=raw.get("observation_end"),
            scene_count=raw.get("scene_count"),
        )

    # -- biomassa (GEDI L4A) ---------------------------------------------------

    def observe_biomass(self, aoi: AreaOfInterest, year: int) -> BiomassRemoteObservation:
        if aoi.lat is not None and not gedi_covers_latitude(aoi.lat):
            return BiomassRemoteObservation(
                coverage_status=CoverageStatus.OUTSIDE_SPATIAL_COVERAGE,
                reason=(
                    f"AOI em latitude {aoi.lat:.4f}, fora da faixa amostrada pelo GEDI "
                    f"(51.6°N a 51.6°S). Nenhuma estimativa de biomassa GEDI é possível."
                ),
            )
        if not gedi_covers_year(year):
            return BiomassRemoteObservation(
                coverage_status=CoverageStatus.OUTSIDE_TEMPORAL_COVERAGE,
                reason=(
                    f"GEDI unavailable for requested period: {year} fora de "
                    f"{GEDI_L4A.temporal_start}..{GEDI_L4A.temporal_end}. "
                    "Nenhuma biomassa é estimada para esse ano."
                ),
            )

        start, end = observation_window(year, expansion_months=self.window_expansion_months)
        try:
            raw, cache_hit, acquired_at = self._cached(
                GEDI_L4A.dataset_id,
                aoi,
                start,
                end,
                lambda: self.client.gedi_biomass_stats(aoi.geojson, start, end),
            )
        except GEEQueryError as exc:
            return BiomassRemoteObservation(
                coverage_status=CoverageStatus.QUERY_FAILED,
                reason=f"Consulta ao GEDI L4A falhou: {exc}. Resultado indisponível, não zero.",
            )

        window = self._window(year, raw)
        sample_count = int(raw.get("sample_count") or 0)
        support = classify_sampling_support(sample_count)
        warnings: list[str] = []

        if sample_count <= 0:
            return BiomassRemoteObservation(
                coverage_status=CoverageStatus.NO_OBSERVATIONS,
                support=support,
                sample_count=0,
                window=window,
                reason=(
                    "insufficient GEDI sampling: nenhum footprint válido na AOI após os "
                    "filtros de qualidade. Biomassa NÃO disponível (não é zero)."
                ),
                provenance=self._provenance(
                    GEDI_L4A,
                    aoi,
                    window,
                    raw,
                    bands=["agbd", "agbd_se"],
                    cache_hit=cache_hit,
                    retrieval_timestamp=acquired_at,
                    sample_count=0,
                ),
            )

        mean_agbd = raw.get("mean_agbd_mg_ha")
        std_agbd = raw.get("std_agbd_mg_ha")
        if mean_agbd is None:
            return BiomassRemoteObservation(
                coverage_status=CoverageStatus.NO_OBSERVATIONS,
                support=support,
                sample_count=sample_count,
                window=window,
                reason="Redução retornou contagem sem média: estatística inconsistente, valor recusado.",
            )

        density_t_ha = mg_ha_to_t_ha(float(mean_agbd))
        total_t = total_dry_biomass_t(density_t_ha, aoi.area_ha)
        uncertainty = sampling_uncertainty_percent(mean_agbd, std_agbd, sample_count)
        sampled_area_ha = sample_count * GEDI_FOOTPRINT_AREA_M2 / M2_PER_HA

        if support is SamplingSupport.VERY_LOW_SUPPORT:
            warnings.append(
                f"very_low_support: {sample_count} footprint(s). A média não representa "
                "a AOI de forma robusta. {rationale}".format(rationale=SAMPLING_SUPPORT_RATIONALE)
            )
        elif support is SamplingSupport.LOW_SUPPORT:
            warnings.append(
                f"low_support: {sample_count} footprints — abaixo do mínimo operacional "
                f"de {USABLE_SUPPORT_MIN_FOOTPRINTS} para tratar a média como utilizável."
            )
        if uncertainty is None:
            warnings.append(
                "Incerteza amostral não estimável (menos de 2 footprints ou dispersão "
                "ausente). Nenhum percentual foi arbitrado."
            )
        warnings.append(
            "Erro de predição do modelo GEDI (agbd_se) preservado em bruto e NÃO "
            "combinado: a correlação entre erros de footprints não é publicada no produto."
        )
        warnings.append(
            "sample_count é a contagem de células de 25 m distintas com footprint "
            "retido no mosaico — estimativa conservadora do número de footprints."
        )

        return BiomassRemoteObservation(
            available=True,
            coverage_status=CoverageStatus.AVAILABLE,
            support=support,
            sample_count=sample_count,
            mean_agbd_mg_ha=mean_agbd,
            median_agbd_mg_ha=raw.get("median_agbd_mg_ha"),
            std_agbd_mg_ha=std_agbd,
            min_agbd_mg_ha=raw.get("min_agbd_mg_ha"),
            max_agbd_mg_ha=raw.get("max_agbd_mg_ha"),
            mean_prediction_se_mg_ha=raw.get("mean_prediction_se_mg_ha"),
            sampled_area_ha=sampled_area_ha,
            sampled_fraction_of_aoi=sampled_area_ha / aoi.area_ha,
            agb_density_t_ha=density_t_ha,
            agb_total_t=total_t,
            sampling_uncertainty_percent=uncertainty,
            uncertainty_available=uncertainty is not None,
            uncertainty_source="GEDI" if uncertainty is not None else None,
            uncertainty_method=SAMPLING_UNCERTAINTY_METHOD if uncertainty is not None else None,
            model_error_included=False,
            window=window,
            warnings=warnings,
            provenance=self._provenance(
                GEDI_L4A,
                aoi,
                window,
                raw,
                bands=["agbd", "agbd_se"],
                cache_hit=cache_hit,
                retrieval_timestamp=acquired_at,
                sample_count=sample_count,
                data_level=DataLevel.PROJECT_SPECIFIC,
                warnings=warnings,
            ),
        )

    # -- dossel (GEDI L2A) -----------------------------------------------------

    def observe_canopy(self, aoi: AreaOfInterest, year: int) -> CanopyRemoteObservation:
        if aoi.lat is not None and not gedi_covers_latitude(aoi.lat):
            return CanopyRemoteObservation(
                coverage_status=CoverageStatus.OUTSIDE_SPATIAL_COVERAGE,
                reason="AOI fora da faixa latitudinal amostrada pelo GEDI.",
            )
        start, end = observation_window(year, expansion_months=self.window_expansion_months)
        try:
            raw, cache_hit, acquired_at = self._cached(
                GEDI_L2A.dataset_id,
                aoi,
                start,
                end,
                lambda: self.client.gedi_canopy_stats(aoi.geojson, start, end),
            )
        except GEEQueryError as exc:
            return CanopyRemoteObservation(
                coverage_status=CoverageStatus.QUERY_FAILED,
                reason=f"Consulta ao GEDI L2A falhou: {exc}. Altura de dossel indisponível.",
            )

        window = self._window(year, raw)
        sample_count = int(raw.get("sample_count") or 0)
        support = classify_sampling_support(sample_count)
        provenance = self._provenance(
            GEDI_L2A,
            aoi,
            window,
            raw,
            bands=[raw.get("metric") or "rh98"],
            cache_hit=cache_hit,
            retrieval_timestamp=acquired_at,
            sample_count=sample_count,
        )
        if sample_count <= 0 or raw.get("mean_canopy_height_m") is None:
            return CanopyRemoteObservation(
                coverage_status=CoverageStatus.NO_OBSERVATIONS,
                support=support,
                sample_count=sample_count,
                window=window,
                provenance=provenance,
                reason="Sem footprints GEDI L2A válidos na AOI: altura de dossel not_available.",
            )
        return CanopyRemoteObservation(
            available=True,
            coverage_status=CoverageStatus.AVAILABLE,
            support=support,
            sample_count=sample_count,
            mean_canopy_height_m=raw.get("mean_canopy_height_m"),
            median_canopy_height_m=raw.get("median_canopy_height_m"),
            std_canopy_height_m=raw.get("std_canopy_height_m"),
            metric=raw.get("metric"),
            window=window,
            provenance=provenance,
            warnings=[
                "Altura de dossel é métrica estrutural (RH). NÃO é convertida em "
                "biomassa nem em carbono por este motor."
            ],
        )

    # -- cobertura da terra (Dynamic World) ------------------------------------

    def observe_land_cover(self, aoi: AreaOfInterest, year: int) -> LandCoverObservation:
        start, end = observation_window(year, expansion_months=self.window_expansion_months)
        try:
            raw, cache_hit, acquired_at = self._cached(
                DYNAMIC_WORLD.dataset_id,
                aoi,
                start,
                end,
                lambda: self.client.dynamic_world_land_cover(aoi.geojson, start, end),
            )
        except GEEQueryError as exc:
            return LandCoverObservation(
                coverage_status=CoverageStatus.QUERY_FAILED,
                reason=f"Consulta ao Dynamic World falhou: {exc}.",
            )

        window = self._window(year, raw)
        counts = raw.get("class_pixel_counts") or {}
        total = sum(counts.values())
        provenance = self._provenance(
            DYNAMIC_WORLD,
            aoi,
            window,
            raw,
            bands=["label", "trees"],
            cache_hit=cache_hit,
            retrieval_timestamp=acquired_at,
        )
        if total <= 0:
            return LandCoverObservation(
                coverage_status=CoverageStatus.NO_OBSERVATIONS,
                window=window,
                provenance=provenance,
                reason="Sem cenas Dynamic World válidas na janela: cobertura da terra indisponível.",
            )
        distribution = {name: value / total * 100 for name, value in counts.items()}
        dominant = max(distribution, key=distribution.get)
        return LandCoverObservation(
            available=True,
            coverage_status=CoverageStatus.AVAILABLE,
            dominant_land_cover=dominant,
            land_cover_distribution_percent=distribution,
            tree_probability_mean=raw.get("tree_probability_mean"),
            window=window,
            provenance=provenance,
            warnings=[
                "Distribuição derivada da moda da banda 'label'; 'trees' é "
                "probabilidade de classe, não percentual de cobertura arbórea medido.",
                "Cobertura da terra é usada como QA, contexto e detecção de "
                "incoerência — nunca como quantidade de carbono.",
            ],
        )

    # -- índices espectrais (Sentinel-2) ---------------------------------------

    def observe_vegetation_indices(
        self, aoi: AreaOfInterest, year: int
    ) -> VegetationIndicators:
        start, end = observation_window(year, expansion_months=self.window_expansion_months)
        try:
            raw, cache_hit, acquired_at = self._cached(
                SENTINEL2_SR.dataset_id,
                aoi,
                start,
                end,
                lambda: self.client.sentinel2_indices(aoi.geojson, start, end),
            )
        except GEEQueryError as exc:
            return VegetationIndicators(
                coverage_status=CoverageStatus.QUERY_FAILED,
                reason=f"Consulta ao Sentinel-2 falhou: {exc}.",
            )

        window = self._window(year, raw)
        provenance = self._provenance(
            SENTINEL2_SR,
            aoi,
            window,
            raw,
            bands=["B2", "B4", "B8", "B11", "B12", "cs"],
            cache_hit=cache_hit,
            retrieval_timestamp=acquired_at,
        )
        scene_count = int(raw.get("scene_count") or 0)
        if scene_count <= 0 or raw.get("ndvi") is None:
            return VegetationIndicators(
                coverage_status=CoverageStatus.NO_OBSERVATIONS,
                window=window,
                provenance=provenance,
                reason=(
                    "Nenhuma cena Sentinel-2 utilizável na janela (ou 100% mascarada "
                    "por nuvem). Índices indisponíveis."
                ),
            )
        valid_fraction = raw.get("valid_fraction")
        warnings = [
            "Índices espectrais são indicadores: NÃO são estoque nem mudança de carbono.",
            raw.get("evi_validation_status", "")
            and "Coeficientes do EVI ainda não conferidos na fonte primária.",
        ]
        return VegetationIndicators(
            available=True,
            coverage_status=CoverageStatus.AVAILABLE,
            ndvi=raw.get("ndvi"),
            evi=raw.get("evi"),
            nbr=raw.get("nbr"),
            ndmi=raw.get("ndmi"),
            mean_cloud_score=raw.get("mean_clear_score"),
            cloud_masked_fraction=(1 - valid_fraction) if valid_fraction is not None else None,
            window=window,
            provenance=provenance,
            warnings=[w for w in warnings if w],
        )

    # -- mudança observada -----------------------------------------------------

    def observe_change(
        self,
        aoi: AreaOfInterest,
        *,
        baseline_year: int,
        current_year: int,
        baseline_indices: Optional[VegetationIndicators] = None,
        current_indices: Optional[VegetationIndicators] = None,
        baseline_land_cover: Optional[LandCoverObservation] = None,
        current_land_cover: Optional[LandCoverObservation] = None,
        baseline_biomass: Optional[BiomassRemoteObservation] = None,
        current_biomass: Optional[BiomassRemoteObservation] = None,
    ) -> ObservedLandChange:
        """Mudança OBSERVACIONAL. Nunca converte espectro em carbono."""
        change = ObservedLandChange(
            baseline_year=baseline_year, current_year=current_year
        )
        warnings: list[str] = []

        def delta(current, baseline):
            if current is None or baseline is None:
                return None
            return current - baseline

        if baseline_indices is not None and current_indices is not None:
            if baseline_indices.available and current_indices.available:
                change.available = True
                change.delta_ndvi = delta(current_indices.ndvi, baseline_indices.ndvi)
                change.delta_nbr = delta(current_indices.nbr, baseline_indices.nbr)
                change.delta_ndmi = delta(current_indices.ndmi, baseline_indices.ndmi)

        if baseline_land_cover is not None and current_land_cover is not None:
            if baseline_land_cover.available and current_land_cover.available:
                change.available = True
                change.baseline_dominant_land_cover = baseline_land_cover.dominant_land_cover
                change.current_dominant_land_cover = current_land_cover.dominant_land_cover
                change.land_cover_changed = (
                    baseline_land_cover.dominant_land_cover
                    != current_land_cover.dominant_land_cover
                )
                change.delta_tree_probability = delta(
                    current_land_cover.tree_probability_mean,
                    baseline_land_cover.tree_probability_mean,
                )

        comparable, reason = biomass_periods_comparable(baseline_biomass, current_biomass)
        change.carbon_change_available = comparable
        change.carbon_change_reason = reason
        if comparable:
            warnings.append(
                "Os conjuntos de footprints GEDI de T0 e T1 NÃO são co-localizados: "
                "a diferença entre médias reflete amostras distintas da mesma AOI, "
                "não a remedição das mesmas unidades amostrais."
            )
        if change.delta_ndvi is not None:
            warnings.append(
                "Variação de NDVI/NBR/NDMI é mudança espectral observada; não vira "
                "mudança de estoque de carbono por multiplicação."
            )
        change.warnings = warnings
        return change

    # -- contrato RemoteSensingCarbonProvider ---------------------------------
    #
    # Assinaturas do Protocol existente (geometry: dict, year: int), para que o
    # provider real seja substituível pelo NullRemoteSensingProvider sem que
    # nada mais no motor precise mudar.

    def estimate_biomass(self, *, geometry: dict, year: int) -> TracedValue:
        from .geometry_service import aoi_from_geojson

        aoi = aoi_from_geojson(geometry)
        observation = self.observe_biomass(aoi, year)
        return biomass_to_traced_value(observation)

    def estimate_canopy(self, *, geometry: dict, year: int) -> TracedValue:
        from .geometry_service import aoi_from_geojson

        aoi = aoi_from_geojson(geometry)
        observation = self.observe_canopy(aoi, year)
        if not observation.available:
            return TracedValue.not_available("m", observation.reason or "dossel indisponível")
        return TracedValue(
            value=observation.mean_canopy_height_m,
            unit="m",
            estimation_type=EstimationType.REMOTE_SENSING,
            source=f"{GEDI_L2A.dataset_id} ({observation.metric})",
            inputs={"sample_count": observation.sample_count},
            notes=list(observation.warnings),
        )

    def estimate_land_cover(self, *, geometry: dict, year: int) -> dict:
        from .geometry_service import aoi_from_geojson

        aoi = aoi_from_geojson(geometry)
        observation = self.observe_land_cover(aoi, year)
        return observation.model_dump(mode="json")

    def estimate_change(
        self, *, geometry: dict, baseline_year: int, current_year: int
    ) -> TracedValue:
        """Mudança de CARBONO — deliberadamente indisponível neste nível.

        Mudança de estoque é calculada pelo Carbon Engine a partir de dois
        inventários comparáveis, não por diferença de observações no provider.
        Os indicadores observacionais estão em ``observe_change``.
        """
        return TracedValue.not_available(
            "tC",
            "Mudança de estoque de carbono não é derivada diretamente do provider: "
            "ela vem do Carbon Engine, comparando dois inventários. Use "
            "observe_change() para os indicadores observacionais de mudança.",
        )


def biomass_to_traced_value(observation: BiomassRemoteObservation) -> TracedValue:
    """Converte a observação em ``TracedValue`` de MATÉRIA SECA (não carbono)."""
    if not observation.available or observation.agb_total_t is None:
        return TracedValue.not_available(
            DRY_MATTER_UNIT, observation.reason or "biomassa GEDI indisponível"
        )
    provenance = observation.provenance
    return TracedValue(
        value=observation.agb_total_t,
        unit=DRY_MATTER_UNIT,
        estimation_type=EstimationType.REMOTE_SENSING,
        data_level=DataLevel.PROJECT_SPECIFIC,
        source=f"{GEDI_L4A.dataset_id} ({GEDI_L4A.name} v{GEDI_L4A.version})",
        tier=2,
        uncertainty_percent=observation.sampling_uncertainty_percent,
        equations_used=["AGB_total = AGBD_density * area"],
        inputs={
            "agbd_mean_mg_ha": observation.mean_agbd_mg_ha,
            "area_ha": provenance.area_ha if provenance else None,
            "sample_count": observation.sample_count,
            "support": observation.support.value,
        },
        notes=[
            "Biomassa AÉREA SECA observada por lidar. A fração de carbono é "
            "aplicada apenas pelo Carbon Engine — nunca aqui.",
            *observation.warnings,
        ],
    )


def biomass_periods_comparable(
    baseline: Optional[BiomassRemoteObservation],
    current: Optional[BiomassRemoteObservation],
) -> tuple:
    """Só há mudança de carbono se AMBOS os períodos têm biomassa utilizável."""
    if baseline is None or current is None:
        return False, "carbon_change = not_available: falta observação de biomassa em um dos períodos."
    if not baseline.available:
        return False, f"carbon_change = not_available: baseline sem biomassa ({baseline.reason})."
    if not current.available:
        return False, f"carbon_change = not_available: período atual sem biomassa ({current.reason})."
    if (
        baseline.support is not SamplingSupport.USABLE
        or current.support is not SamplingSupport.USABLE
    ):
        return False, (
            "carbon_change = not_available: suporte amostral insuficiente em ao menos "
            f"um período (baseline={baseline.support.value}, atual={current.support.value})."
        )
    return True, "Observações de biomassa comparáveis nos dois períodos."


def check_land_cover_consistency(
    declared_land_use: str, land_cover: LandCoverObservation
) -> LandCoverConsistency:
    """Confronta uso declarado com cobertura observada.

    Incoerência grave (AOI dominada por água, construção ou neve) é BLOQUEANTE:
    o motor não calcula estoque de biomassa em silêncio nesse caso.
    """
    if not land_cover.available or land_cover.dominant_land_cover is None:
        return LandCoverConsistency(
            checked=False,
            declared_land_use=declared_land_use,
            message="Cobertura da terra indisponível: consistência não verificada.",
        )

    dominant = land_cover.dominant_land_cover
    percent = land_cover.land_cover_distribution_percent.get(dominant)
    expected = LAND_USE_EXPECTED_COVER.get(declared_land_use)

    if dominant in BLOCKING_COVER_CLASSES and (percent or 0) >= DOMINANCE_THRESHOLD_PERCENT:
        return LandCoverConsistency(
            checked=True,
            consistent=False,
            declared_land_use=declared_land_use,
            observed_dominant=dominant,
            observed_percent=percent,
            severity="error",
            blocking=True,
            message=(
                f"Incoerência bloqueante: uso declarado '{declared_land_use}' mas "
                f"{percent:.1f}% da AOI é '{dominant}'. Estimativa de biomassa não "
                "prossegue automaticamente."
            ),
        )

    if expected is None or dominant in expected:
        return LandCoverConsistency(
            checked=True,
            consistent=True,
            declared_land_use=declared_land_use,
            observed_dominant=dominant,
            observed_percent=percent,
            severity="info",
            message=f"Cobertura dominante '{dominant}' compatível com '{declared_land_use}'.",
        )

    return LandCoverConsistency(
        checked=True,
        consistent=False,
        declared_land_use=declared_land_use,
        observed_dominant=dominant,
        observed_percent=percent,
        severity="warning",
        blocking=False,
        message=(
            f"Cobertura dominante observada '{dominant}' ({percent:.1f}%) não é típica de "
            f"'{declared_land_use}'. Resultado mantido, incoerência registrada."
        ),
    )


def observe_all(
    provider: GoogleEarthEngineCarbonProvider,
    aoi: AreaOfInterest,
    *,
    declared_land_use: str,
    current_year: int,
    baseline_year: Optional[int] = None,
) -> RemoteSensingBundle:
    """Coleta o pacote completo de observações para a AOI."""
    bundle = RemoteSensingBundle(
        aoi=aoi, current_year=current_year, baseline_year=baseline_year
    )
    bundle.biomass = provider.observe_biomass(aoi, current_year)
    bundle.canopy = provider.observe_canopy(aoi, current_year)
    bundle.land_cover = provider.observe_land_cover(aoi, current_year)
    bundle.vegetation_indices = provider.observe_vegetation_indices(aoi, current_year)

    if baseline_year is not None:
        bundle.baseline_biomass = provider.observe_biomass(aoi, baseline_year)
        bundle.baseline_land_cover = provider.observe_land_cover(aoi, baseline_year)
        bundle.baseline_vegetation_indices = provider.observe_vegetation_indices(
            aoi, baseline_year
        )
        bundle.change = provider.observe_change(
            aoi,
            baseline_year=baseline_year,
            current_year=current_year,
            baseline_indices=bundle.baseline_vegetation_indices,
            current_indices=bundle.vegetation_indices,
            baseline_land_cover=bundle.baseline_land_cover,
            current_land_cover=bundle.land_cover,
            baseline_biomass=bundle.baseline_biomass,
            current_biomass=bundle.biomass,
        )

    bundle.consistency = check_land_cover_consistency(declared_land_use, bundle.land_cover)

    warnings: list[str] = []
    for observation in (bundle.biomass, bundle.canopy, bundle.land_cover, bundle.vegetation_indices):
        warnings.extend(observation.warnings)
    if bundle.consistency.message and bundle.consistency.severity != "info":
        warnings.append(bundle.consistency.message)
    if bundle.change.warnings:
        warnings.extend(bundle.change.warnings)
    bundle.warnings = list(dict.fromkeys(warnings))

    # Registro documental do papel admissível de cada índice espectral.
    if bundle.vegetation_indices.available:
        for index_name in ("ndvi", "evi", "nbr", "ndmi"):
            role = vegetation_index_role(
                index_name, getattr(bundle.vegetation_indices, index_name)
            )
            assert role["carbon_equivalent"] is None  # invariante do contrato
    return bundle
