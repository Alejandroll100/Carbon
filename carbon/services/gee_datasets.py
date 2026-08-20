"""Catálogo DECLARADO dos datasets do Earth Engine utilizados.

Mesma filosofia da base de fatores: nenhum dataset é usado por id "solto"
dentro de uma função. Cada produto é um objeto com id, bandas, unidade,
resolução, período de disponibilidade, filtros de qualidade, limitações e
referência bibliográfica.

Cada campo abaixo foi conferido na PÁGINA OFICIAL DO CATÁLOGO do Earth Engine
em 2026-08-19. O que NÃO foi lido no documento primário está declarado em
``unverified_items`` — não em silêncio.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

#: Limite latitudinal da órbita da ISS, e portanto da amostragem GEDI.
#: Conferido na descrição oficial do produto (bbox do catálogo: -51.6 a 51.6).
GEDI_LATITUDE_ABS_LIMIT = 51.6
#: Diâmetro nominal do footprint GEDI (descrição oficial: ~25 m).
GEDI_FOOTPRINT_DIAMETER_M = 25.0
#: Fator de escala das bandas de reflectância do Sentinel-2 L2A no EE
#: (coluna "Scale" da tabela de bandas: 0.0001 para B1..B12).
SENTINEL2_REFLECTANCE_SCALE = 0.0001


class DatasetDescriptor(BaseModel):
    """Descrição auditável de um produto geoespacial."""

    dataset_id: str
    name: str
    version: Optional[str] = None
    asset_type: str  # "ImageCollection" | "Image"
    purpose: str
    variables: list[str] = Field(default_factory=list)
    units: Optional[str] = None
    spatial_resolution_m: Optional[float] = None
    temporal_start: Optional[str] = None
    temporal_end: Optional[str] = None
    spatial_coverage: Optional[str] = None
    quality_filters: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    reference_id: Optional[str] = None
    source_url: Optional[str] = None
    #: O que NÃO foi conferido no documento primário.
    unverified_items: list[str] = Field(default_factory=list)

    def provenance_fields(self) -> dict:
        return {
            "dataset_id": self.dataset_id,
            "dataset_name": self.name,
            "dataset_version": self.version,
            "units": self.units,
            "spatial_resolution_m": self.spatial_resolution_m,
            "temporal_coverage": f"{self.temporal_start} .. {self.temporal_end}",
            "reference_id": self.reference_id,
            "source_url": self.source_url,
        }


GEDI_L4A = DatasetDescriptor(
    dataset_id="LARSE/GEDI/GEDI04_A_002_MONTHLY",
    name="GEDI L4A Raster Aboveground Biomass Density",
    version="2.1",
    asset_type="ImageCollection",
    purpose="Densidade de biomassa AÉREA (AGBD) estimada por footprint lidar.",
    variables=["agbd", "agbd_se", "l4_quality_flag", "degrade_flag", "sensitivity"],
    units="Mg/ha (matéria seca aérea)",
    spatial_resolution_m=GEDI_FOOTPRINT_DIAMETER_M,
    temporal_start="2019-03-25",
    temporal_end="2025-07-01",
    spatial_coverage="51.6°N a 51.6°S (órbita da ISS)",
    quality_filters=[
        "l4_quality_flag == 1 (máscara oficial do exemplo do catálogo)",
        "degrade_flag == 0 (máscara oficial do exemplo do catálogo)",
    ],
    limitations=[
        "Amostragem por transecto, NÃO cobertura contínua: uma AOI pode ter zero footprints.",
        "Sem cobertura acima de 51.6° de latitude em qualquer hemisfério.",
        "Sem cobertura antes de 2019-03-25: não existe AGBD GEDI para baseline histórico.",
        "O raster mensal é uma rasterização dos footprints; footprints repetidos "
        "na mesma célula de 25 m em meses diferentes colapsam no mosaico.",
        "agbd_se é erro padrão de predição do MODELO por footprint; a correlação "
        "entre erros de footprints não é publicada no raster e por isso não é "
        "combinada pelo motor.",
    ],
    reference_id="GEE_GEDI_L4A_RASTER",
    source_url=(
        "https://developers.google.com/earth-engine/datasets/catalog/"
        "LARSE_GEDI_GEDI04_A_002_MONTHLY"
    ),
    unverified_items=[
        "ATBD/User Guide do ORNL DAAC não lido: definição formal de 'dry biomass' "
        "e faixa de calibração por PFT vêm da página do catálogo, não do documento técnico.",
        "DOI do produto não conferido no documento primário.",
    ],
)

GEDI_L2A = DatasetDescriptor(
    dataset_id="LARSE/GEDI/GEDI02_A_002_MONTHLY",
    name="GEDI L2A Raster Canopy Top Height (Relative Height metrics)",
    version="2",
    asset_type="ImageCollection",
    purpose="Altura do dossel a partir de métricas de altura relativa (RH).",
    variables=["rh98", "quality_flag", "degrade_flag", "sensitivity"],
    units="m",
    spatial_resolution_m=GEDI_FOOTPRINT_DIAMETER_M,
    temporal_start="2019-03-25",
    temporal_end="2025-02-01",
    spatial_coverage="51.6°N a 51.6°S (órbita da ISS)",
    quality_filters=[
        "quality_flag == 1 (1=válido, 0=inválido)",
        "degrade_flag == 0",
    ],
    limitations=[
        "Mesmas restrições de amostragem e cobertura do L4A.",
        "rh98 é altura relativa do retorno, NÃO altura de árvore medida em campo.",
        "Altura de dossel NÃO é convertida em biomassa por este motor.",
    ],
    reference_id="GEE_GEDI_L2A_RASTER",
    source_url=(
        "https://developers.google.com/earth-engine/datasets/catalog/"
        "LARSE_GEDI_GEDI02_A_002_MONTHLY"
    ),
    unverified_items=[
        "Tabela completa de bandas não lida integralmente: a existência da banda "
        "rh98 foi observada em uso documentado, não na tabela oficial. Se a banda "
        "não existir na coleção, a consulta falha explicitamente e retorna "
        "not_available — nunca um número inventado.",
    ],
)

SENTINEL2_SR = DatasetDescriptor(
    dataset_id="COPERNICUS/S2_SR_HARMONIZED",
    name="Harmonized Sentinel-2 MSI Level-2A Surface Reflectance",
    version="L2A harmonized",
    asset_type="ImageCollection",
    purpose="Contexto espectral da vegetação, índices e detecção de mudança.",
    variables=["B2", "B4", "B8", "B11", "B12"],
    units="reflectância (DN x 0.0001)",
    spatial_resolution_m=10.0,
    temporal_start="2017-03-28",
    temporal_end="presente",
    spatial_coverage="-56° a 83° de latitude",
    quality_filters=[
        "Cloud Score+ 'cs' >= limiar de pixel claro (linkCollection)",
    ],
    limitations=[
        "Cobertura L2A de 2017-2018 não é global (aviso do próprio catálogo).",
        "Índice espectral NÃO é estoque de carbono e nunca é convertido em tC.",
        "B11/B12 têm 20 m; NDMI e NBR são calculados na escala mais grosseira do par.",
    ],
    reference_id="GEE_SENTINEL2_SR_HARMONIZED",
    source_url=(
        "https://developers.google.com/earth-engine/datasets/catalog/"
        "COPERNICUS_S2_SR_HARMONIZED"
    ),
)

CLOUD_SCORE_PLUS = DatasetDescriptor(
    dataset_id="GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED",
    name="Cloud Score+ S2_HARMONIZED V1",
    version="V1",
    asset_type="ImageCollection",
    purpose="Máscara de nuvem/sombra para o Sentinel-2.",
    variables=["cs", "cs_cdf"],
    units="adimensional [0,1]",
    spatial_resolution_m=10.0,
    temporal_start="2015-06-27",
    temporal_end="presente",
    spatial_coverage="mesma do Sentinel-2",
    quality_filters=["cs >= limiar de pixel claro"],
    limitations=[
        "Produzido a partir do L1C; aplicável a L1C ou L2A.",
        "Limiar de corte é decisão do analista; o catálogo indica faixa usual 0.50-0.65.",
    ],
    reference_id="GEE_CLOUD_SCORE_PLUS",
    source_url=(
        "https://developers.google.com/earth-engine/datasets/catalog/"
        "GOOGLE_CLOUD_SCORE_PLUS_V1_S2_HARMONIZED"
    ),
)

DYNAMIC_WORLD = DatasetDescriptor(
    dataset_id="GOOGLE/DYNAMICWORLD/V1",
    name="Dynamic World V1 Near Real-Time Land Use Land Cover",
    version="V1",
    asset_type="ImageCollection",
    purpose="Uso/cobertura da terra para QA, contexto e detecção de incoerência.",
    variables=[
        "label",
        "water",
        "trees",
        "grass",
        "flooded_vegetation",
        "crops",
        "shrub_and_scrub",
        "built",
        "bare",
        "snow_and_ice",
    ],
    units="classe (label) / probabilidade [0,1]",
    spatial_resolution_m=10.0,
    temporal_start="2015-06-27",
    temporal_end="presente",
    spatial_coverage="global",
    quality_filters=[
        "predições geradas apenas para cenas S2 L1C com CLOUDY_PIXEL_PERCENTAGE <= 35%",
    ],
    limitations=[
        "As bandas de probabilidade são saída de classificador, NÃO probabilidade calibrada.",
        "'trees' é probabilidade de classe, NÃO percentual de cobertura arbórea medido.",
        "Serve como QA e contexto; nunca entra no cálculo de carbono como quantidade.",
    ],
    reference_id="GEE_DYNAMIC_WORLD",
    source_url=(
        "https://developers.google.com/earth-engine/datasets/catalog/"
        "GOOGLE_DYNAMICWORLD_V1"
    ),
)

ESA_WORLDCOVER = DatasetDescriptor(
    dataset_id="ESA/WorldCover/v200",
    name="ESA WorldCover 10m v200 (2021)",
    version="v200",
    asset_type="ImageCollection",
    purpose="Referência estática de cobertura da terra quando Dynamic World não se aplica.",
    variables=["Map"],
    units="classe",
    spatial_resolution_m=10.0,
    temporal_start="2021-01-01",
    temporal_end="2022-01-01",
    spatial_coverage="global",
    quality_filters=[],
    limitations=[
        "Mapa de ANO ÚNICO (2021). Não representa o ano solicitado pelo usuário.",
        "v100 (2020) e v200 (2021) usam algoritmos diferentes: a diferença entre "
        "os dois mapas NÃO é mudança de cobertura.",
    ],
    reference_id="GEE_ESA_WORLDCOVER_V200",
    source_url=(
        "https://developers.google.com/earth-engine/datasets/catalog/ESA_WorldCover_v200"
    ),
)

#: Classes do Dynamic World na ordem do índice da banda ``label`` (0..8),
#: conferida na documentação oficial do produto.
DYNAMIC_WORLD_CLASSES = [
    "water",
    "trees",
    "grass",
    "flooded_vegetation",
    "crops",
    "shrub_and_scrub",
    "built",
    "bare",
    "snow_and_ice",
]

#: Tabela de classes da banda ``Map`` do ESA WorldCover v200.
ESA_WORLDCOVER_CLASSES = {
    10: "tree_cover",
    20: "shrubland",
    30: "grassland",
    40: "cropland",
    50: "built_up",
    60: "bare_sparse_vegetation",
    70: "snow_and_ice",
    80: "permanent_water",
    90: "herbaceous_wetland",
    95: "mangroves",
    100: "moss_and_lichen",
}

ALL_DATASETS = [
    GEDI_L4A,
    GEDI_L2A,
    SENTINEL2_SR,
    CLOUD_SCORE_PLUS,
    DYNAMIC_WORLD,
    ESA_WORLDCOVER,
]


def dataset_catalog() -> list[dict]:
    """Catálogo serializável, para o endpoint de metadados e o relatório."""
    return [d.model_dump() for d in ALL_DATASETS]


def gedi_covers_latitude(lat: float) -> bool:
    """GEDI não amostra fora da faixa da órbita da ISS."""
    return abs(lat) <= GEDI_LATITUDE_ABS_LIMIT


def gedi_covers_year(year: int) -> bool:
    """Ano dentro do período de disponibilidade declarado do produto L4A."""
    start_year = int(GEDI_L4A.temporal_start.split("-")[0])
    end_year = int(GEDI_L4A.temporal_end.split("-")[0])
    return start_year <= year <= end_year
