"""Modelos da camada de sensoriamento remoto.

Regras que estes modelos existem para tornar impossíveis de violar em silêncio:

* ausência é ``available=False`` + motivo, nunca ``0``;
* toda observação carrega ``RemoteSensingProvenance`` completa;
* incerteza tem ORIGEM declarada e ``uncertainty_available`` explícito —
  nenhum ±10% é fabricado;
* índice espectral vive em ``VegetationIndicators``, que não tem nenhum campo
  em tonelada de carbono, por construção;
* mudança OBSERVADA (espectral/cobertura) e mudança de ESTOQUE DE CARBONO são
  dois objetos diferentes e nunca se convertem um no outro.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from .enums import DataLevel, EstimationType


class GeometrySource(str, Enum):
    """De onde veio a geometria da AOI. Entra no audit trail."""

    POINT_EQUIVALENT_AREA_BUFFER = "point + equivalent-area buffer"
    USER_POLYGON = "user_polygon"


class AreaSource(str, Enum):
    DECLARED_BY_USER = "declared_by_user"
    GEODESIC_COMPUTED_GEE = "geodesic_computed_gee"
    LOCAL_SPHERICAL_APPROXIMATION = "local_spherical_approximation"


class SamplingSupport(str, Enum):
    """Suporte amostral do GEDI para a AOI.

    Limiares operacionais GEØ.IA (não são fator IPCC nem valor de literatura);
    justificativa em ``gee_provider.SAMPLING_SUPPORT_RATIONALE``.
    """

    UNAVAILABLE = "unavailable"
    VERY_LOW_SUPPORT = "very_low_support"
    LOW_SUPPORT = "low_support"
    USABLE = "usable"


class CoverageStatus(str, Enum):
    AVAILABLE = "available"
    NO_OBSERVATIONS = "no_observations"
    OUTSIDE_SPATIAL_COVERAGE = "outside_spatial_coverage"
    OUTSIDE_TEMPORAL_COVERAGE = "outside_temporal_coverage"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    QUERY_FAILED = "query_failed"


class AreaOfInterest(BaseModel):
    """AOI resolvida, com a origem da geometria e da área registradas."""

    geojson: dict
    geometry_source: GeometrySource
    area_ha: float = Field(gt=0)
    area_source: AreaSource
    geometry_hash: str
    lat: Optional[float] = None
    lon: Optional[float] = None
    buffer_radius_m: Optional[float] = None
    declared_area_ha: Optional[float] = None
    notes: list[str] = Field(default_factory=list)


class ObservationWindow(BaseModel):
    """Janela realmente observada — distinta da janela pedida.

    O usuário precisa saber que pediu 2024 e recebeu, por exemplo,
    2024-01-01..2024-12-31 com 37 cenas, ou nenhuma.
    """

    requested_year: int
    requested_start: str
    requested_end: str
    actual_observation_start: Optional[str] = None
    actual_observation_end: Optional[str] = None
    scene_count: Optional[int] = None


class RemoteSensingProvenance(BaseModel):
    """Proveniência obrigatória de todo dado vindo do Earth Engine."""

    provider: str = "google_earth_engine"
    dataset_id: str
    dataset_name: str
    dataset_version: Optional[str] = None
    bands: list[str] = Field(default_factory=list)
    units: Optional[str] = None
    spatial_resolution_m: Optional[float] = None
    temporal_coverage: Optional[str] = None
    requested_year: Optional[int] = None
    observation_start: Optional[str] = None
    observation_end: Optional[str] = None
    scene_count: Optional[int] = None
    retrieval_timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    geometry_hash: Optional[str] = None
    geometry_source: Optional[str] = None
    area_ha: Optional[float] = None
    scale_m: Optional[float] = None
    reducer: Optional[str] = None
    max_pixels: Optional[float] = None
    tile_scale: Optional[int] = None
    sample_count: Optional[int] = None
    quality_filters: list[str] = Field(default_factory=list)
    estimation_type: EstimationType = EstimationType.REMOTE_SENSING
    data_level: Optional[DataLevel] = None
    reference_id: Optional[str] = None
    source_url: Optional[str] = None
    cache_hit: bool = False
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class BiomassRemoteObservation(BaseModel):
    """Biomassa AÉREA observada por lidar (GEDI L4A).

    ``agb_total_t`` é MATÉRIA SECA AÉREA, não carbono. A fração de carbono é
    aplicada exclusivamente pelo Carbon Engine, uma única vez.
    """

    available: bool = False
    coverage_status: CoverageStatus = CoverageStatus.NO_OBSERVATIONS
    support: SamplingSupport = SamplingSupport.UNAVAILABLE
    sample_count: int = 0
    mean_agbd_mg_ha: Optional[float] = None
    median_agbd_mg_ha: Optional[float] = None
    std_agbd_mg_ha: Optional[float] = None
    min_agbd_mg_ha: Optional[float] = None
    max_agbd_mg_ha: Optional[float] = None
    mean_prediction_se_mg_ha: Optional[float] = None
    sampled_area_ha: Optional[float] = None
    sampled_fraction_of_aoi: Optional[float] = None
    #: Densidade escolhida como estimador do valor médio da AOI (Mg/ha == t/ha).
    agb_density_t_ha: Optional[float] = None
    agb_total_t: Optional[float] = None
    #: Meia-largura do IC 95% relativa, SÓ da componente amostral.
    sampling_uncertainty_percent: Optional[float] = None
    uncertainty_available: bool = False
    uncertainty_source: Optional[str] = None
    uncertainty_method: Optional[str] = None
    #: O erro do modelo alométrico do GEDI NÃO entra na incerteza propagada.
    model_error_included: bool = False
    window: Optional[ObservationWindow] = None
    provenance: Optional[RemoteSensingProvenance] = None
    reason: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)


class CanopyRemoteObservation(BaseModel):
    available: bool = False
    coverage_status: CoverageStatus = CoverageStatus.NO_OBSERVATIONS
    support: SamplingSupport = SamplingSupport.UNAVAILABLE
    sample_count: int = 0
    mean_canopy_height_m: Optional[float] = None
    median_canopy_height_m: Optional[float] = None
    std_canopy_height_m: Optional[float] = None
    metric: Optional[str] = None
    window: Optional[ObservationWindow] = None
    provenance: Optional[RemoteSensingProvenance] = None
    reason: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)


class LandCoverObservation(BaseModel):
    available: bool = False
    coverage_status: CoverageStatus = CoverageStatus.NO_OBSERVATIONS
    dominant_land_cover: Optional[str] = None
    land_cover_distribution_percent: dict[str, float] = Field(default_factory=dict)
    #: Média da banda de probabilidade 'trees' do Dynamic World.
    #: NÃO é percentual de cobertura arbórea medido.
    tree_probability_mean: Optional[float] = None
    window: Optional[ObservationWindow] = None
    provenance: Optional[RemoteSensingProvenance] = None
    reason: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)


class VegetationIndicators(BaseModel):
    """Índices espectrais.

    Por construção este modelo NÃO tem campo em tC, tCO2e ou biomassa.
    Um índice espectral é contexto, QA, detecção de mudança ou feature de
    modelo — nunca uma quantidade de carbono.
    """

    available: bool = False
    coverage_status: CoverageStatus = CoverageStatus.NO_OBSERVATIONS
    ndvi: Optional[float] = None
    evi: Optional[float] = None
    nbr: Optional[float] = None
    ndmi: Optional[float] = None
    mean_cloud_score: Optional[float] = None
    cloud_masked_fraction: Optional[float] = None
    allowed_uses: list[str] = Field(
        default_factory=lambda: [
            "vegetation_indicator",
            "change_indicator",
            "model_feature",
            "quality_assurance",
        ]
    )
    forbidden_uses: list[str] = Field(
        default_factory=lambda: ["direct_carbon_conversion"]
    )
    carbon_equivalent: None = None
    window: Optional[ObservationWindow] = None
    provenance: Optional[RemoteSensingProvenance] = None
    reason: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)


class ObservedLandChange(BaseModel):
    """Mudança OBSERVADA — espectral e de cobertura. Não é mudança de carbono."""

    available: bool = False
    baseline_year: Optional[int] = None
    current_year: Optional[int] = None
    delta_ndvi: Optional[float] = None
    delta_nbr: Optional[float] = None
    delta_ndmi: Optional[float] = None
    delta_tree_probability: Optional[float] = None
    baseline_dominant_land_cover: Optional[str] = None
    current_dominant_land_cover: Optional[str] = None
    land_cover_changed: Optional[bool] = None
    interpretation: str = (
        "Indicadores observacionais de mudança de vegetação/cobertura. "
        "NÃO são mudança de estoque de carbono e não são convertidos em tC."
    )
    carbon_change_available: bool = False
    carbon_change_reason: Optional[str] = None
    provenance: Optional[RemoteSensingProvenance] = None
    warnings: list[str] = Field(default_factory=list)


class LandCoverConsistency(BaseModel):
    """Confronto entre uso da terra DECLARADO e cobertura OBSERVADA."""

    checked: bool = False
    consistent: Optional[bool] = None
    declared_land_use: Optional[str] = None
    observed_dominant: Optional[str] = None
    observed_percent: Optional[float] = None
    severity: str = "info"  # "info" | "warning" | "error"
    blocking: bool = False
    message: Optional[str] = None


class RemoteSensingBundle(BaseModel):
    """Todas as observações de uma AOI em um ano, mais o baseline opcional."""

    aoi: AreaOfInterest
    current_year: int
    baseline_year: Optional[int] = None
    biomass: BiomassRemoteObservation = Field(default_factory=BiomassRemoteObservation)
    baseline_biomass: Optional[BiomassRemoteObservation] = None
    canopy: CanopyRemoteObservation = Field(default_factory=CanopyRemoteObservation)
    land_cover: LandCoverObservation = Field(default_factory=LandCoverObservation)
    baseline_land_cover: Optional[LandCoverObservation] = None
    vegetation_indices: VegetationIndicators = Field(default_factory=VegetationIndicators)
    baseline_vegetation_indices: Optional[VegetationIndicators] = None
    change: ObservedLandChange = Field(default_factory=ObservedLandChange)
    consistency: LandCoverConsistency = Field(default_factory=LandCoverConsistency)
    warnings: list[str] = Field(default_factory=list)


class BiomassSourceLevel(str, Enum):
    """Hierarquia de fontes de biomassa, da mais forte para a mais fraca.

    A ordem é a do §16 do escopo. Um nível mais fraco NUNCA substitui um mais
    forte em silêncio: a escolha e os níveis recusados ficam na proveniência.
    """

    FIELD_MEASUREMENT = "field_measurement"
    PROJECT_CALIBRATED_MODEL = "project_specific_calibrated_model"
    GEDI_VALID_OBSERVATIONS = "gedi_valid_observations"
    VALIDATED_BIOMASS_RASTER = "validated_biomass_raster_model"
    IPCC_REGIONAL_DEFAULT = "ipcc_regional_default"
    UNAVAILABLE = "unavailable"


BIOMASS_SOURCE_PRIORITY: dict[str, int] = {
    BiomassSourceLevel.FIELD_MEASUREMENT.value: 1,
    BiomassSourceLevel.PROJECT_CALIBRATED_MODEL.value: 2,
    BiomassSourceLevel.GEDI_VALID_OBSERVATIONS.value: 3,
    BiomassSourceLevel.VALIDATED_BIOMASS_RASTER.value: 4,
    BiomassSourceLevel.IPCC_REGIONAL_DEFAULT.value: 5,
    BiomassSourceLevel.UNAVAILABLE.value: 6,
}


class BiomassSourceDecision(BaseModel):
    """Qual fonte de biomassa foi escolhida, e por que as outras não."""

    selected: BiomassSourceLevel
    reason: str
    rejected: list[dict] = Field(default_factory=list)
    delegated_to_engine: bool = False
