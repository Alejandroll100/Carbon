"""Enumerações centrais. Nenhuma regra de domínio codificada em endpoints."""

from __future__ import annotations

from enum import Enum


class LandUse(str, Enum):
    NATURAL_FOREST = "natural_forest"
    SECONDARY_FOREST = "secondary_forest"
    PLANTED_FOREST = "planted_forest"
    REFORESTATION = "reforestation"
    FOREST_RESTORATION = "forest_restoration"
    AGROFORESTRY = "agroforestry"
    CROPLAND = "cropland"
    PASTURE = "pasture"
    SILVOPASTORAL = "silvopastoral"
    DEGRADED_LAND = "degraded_land"
    OTHER = "other"


class CarbonPool(str, Enum):
    ABOVEGROUND = "aboveground_biomass"
    BELOWGROUND = "belowground_biomass"
    DEADWOOD = "deadwood"
    LITTER = "litter"
    SOIL = "soil_organic_carbon"


class EstimationType(str, Enum):
    """Origem epistemológica de um valor. Nunca omitir."""

    MEASURED = "measured"
    MODELLED = "modelled"
    ESTIMATED = "estimated"
    DEFAULT_FACTOR = "default_factor"
    REMOTE_SENSING = "remote_sensing"
    NOT_AVAILABLE = "not_available"


class DataLevel(str, Enum):
    """Hierarquia de preferência de dados. Ordem = prioridade de seleção."""

    MEASURED = "measured"
    PROJECT_SPECIFIC = "project_specific"
    SPECIES_SPECIFIC = "species_specific"
    REGIONAL = "regional"
    NATIONAL = "national"
    BIOME_SPECIFIC = "biome_specific"
    CLIMATE_SPECIFIC = "climate_specific"
    IPCC_DEFAULT = "ipcc_default"
    SCIENTIFIC_PROXY = "scientifically_valid_proxy"


DATA_LEVEL_PRIORITY: dict[str, int] = {
    DataLevel.MEASURED.value: 1,
    DataLevel.PROJECT_SPECIFIC.value: 2,
    DataLevel.SPECIES_SPECIFIC.value: 3,
    DataLevel.REGIONAL.value: 4,
    DataLevel.NATIONAL.value: 5,
    DataLevel.BIOME_SPECIFIC.value: 6,
    DataLevel.CLIMATE_SPECIFIC.value: 7,
    DataLevel.IPCC_DEFAULT.value: 8,
    DataLevel.SCIENTIFIC_PROXY.value: 9,
}


class MethodologyTier(int, Enum):
    TIER_1 = 1
    TIER_2 = 2
    TIER_3 = 3


class CalculationMode(str, Enum):
    QUICK_ESTIMATE = "quick_estimate"
    INVENTORY = "inventory"
    ADVANCED = "advanced"


class ValidationStatus(str, Enum):
    """Status de validação científica de um fator/equação.

    EXACT_CONSTANT
        Constante física/estequiométrica (ex.: 44/12). Não requer validação.
    VALIDATED
        Valor conferido contra a fonte primária por um revisor humano do
        projeto e registrado em ``validated_by`` / ``validated_at``.
    NO_DEFAULT_AVAILABLE
        AUSÊNCIA VALIDADA: a fonte primária foi consultada e declara que não
        existe valor default para este caso. Não é lacuna por falta de
        pesquisa — é um resultado científico negativo, e o motor o reporta
        como tal.
    PROJECT_SUPPLIED
        Valor fornecido pelo próprio projeto/cliente (medição de campo ou
        parâmetro específico). Não requer validação bibliográfica; a
        responsabilidade pelo dado é do projeto.
    REQUIRES_VALIDATION
        Valor presente na base como PLACEHOLDER ESTRUTURAL. A referência
        bibliográfica aponta onde conferir, mas a transcrição numérica ainda
        NÃO foi verificada contra o documento primário. Não usar em entrega
        a cliente sem conferência.
    """

    EXACT_CONSTANT = "exact_constant"
    VALIDATED = "validated"
    NO_DEFAULT_AVAILABLE = "no_default_available"
    PROJECT_SUPPLIED = "project_supplied"
    REQUIRES_VALIDATION = "REQUIRES_VALIDATION"


class ResultStatus(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"


class EventType(str, Enum):
    DEFORESTATION = "deforestation"
    FOREST_DEGRADATION = "forest_degradation"
    FIRE = "fire"
    BIOMASS_REMOVAL = "biomass_removal"
    HARVEST = "harvest"
    MORTALITY = "mortality"
    LAND_CONVERSION = "land_conversion"
    SOIL_CARBON_LOSS = "soil_carbon_loss"


class OperationalEmissionSource(str, Enum):
    DIESEL = "diesel"
    GASOLINE = "gasoline"
    FERTILIZER = "fertilizer"
    ELECTRICITY = "electricity"
    MACHINERY = "machinery"
    IRRIGATION = "irrigation"
    TRANSPORT = "transport"


class ComponentType(str, Enum):
    TREE = "tree"
    SHRUB = "shrub"
    CROP = "crop"
    PASTURE = "pasture"
    SOIL = "soil"


class ConfidenceClass(str, Enum):
    VERY_LOW = "very_low"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


class IPCCClimateRegion(str, Enum):
    """Regiões climáticas do IPCC (2006 Vol.4 Cap.3 Anexo 3A.5; linhas da Tabela 2.3).

    O motor NÃO infere a região climática a partir de coordenadas: o esquema de
    classificação (temperatura média, precipitação, elevação, geada,
    evapotranspiração potencial) está no Anexo 3A.5, que não foi transcrito.
    A região é entrada obrigatória do projeto.
    """

    BOREAL = "boreal"
    COLD_TEMPERATE_DRY = "cold_temperate_dry"
    COLD_TEMPERATE_MOIST = "cold_temperate_moist"
    WARM_TEMPERATE_DRY = "warm_temperate_dry"
    WARM_TEMPERATE_MOIST = "warm_temperate_moist"
    TROPICAL_DRY = "tropical_dry"
    TROPICAL_MOIST = "tropical_moist"
    TROPICAL_WET = "tropical_wet"
    TROPICAL_MONTANE = "tropical_montane"


class IPCCSoilType(str, Enum):
    """Classes de solo do IPCC (colunas da Tabela 2.3)."""

    HAC = "HAC"
    LAC = "LAC"
    SANDY = "sandy"
    SPODIC = "spodic"
    VOLCANIC = "volcanic"
    WETLAND = "wetland"


class TillageManagement(str, Enum):
    FULL = "full_tillage"
    REDUCED = "reduced_tillage"
    NO_TILL = "no_till"


class CarbonInputLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH_WITHOUT_MANURE = "high_without_manure"
    HIGH_WITH_MANURE = "high_with_manure"


class CroplandSystem(str, Enum):
    """Níveis de F_LU da Tabela 5.5."""

    LONG_TERM_CULTIVATED = "long_term_cultivated"
    PADDY_RICE = "paddy_rice"
    PERENNIAL_TREE_CROP = "perennial_tree_crop"
    SET_ASIDE = "set_aside"


#: Decomposição de cada região climática da Tabela 2.3 nos regimes usados pela
#: Tabela 5.5 (temperatura, umidade). Transcrito da própria Tabela 5.5, cuja
#: nota 1 define: "wet moisture regime corresponds to the combined moist and
#: wet zones in the tropics and moist zone in temperate regions".
CLIMATE_REGION_TO_REGIME: dict[str, tuple[str, str]] = {
    "boreal": ("temperate_boreal", "moist"),
    "cold_temperate_dry": ("temperate_boreal", "dry"),
    "cold_temperate_moist": ("temperate_boreal", "moist"),
    "warm_temperate_dry": ("temperate_boreal", "dry"),
    "warm_temperate_moist": ("temperate_boreal", "moist"),
    "tropical_dry": ("tropical", "dry"),
    "tropical_moist": ("tropical", "moist_wet"),
    "tropical_wet": ("tropical", "moist_wet"),
    "tropical_montane": ("tropical_montane", None),
}
