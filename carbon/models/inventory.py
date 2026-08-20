"""Modelos de entrada de inventário (observações de campo).

Cada observação declara sua origem (``estimation_type``). Ausência de dado é
``None`` e nunca vira zero.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from ..utils.validation import (
    validate_bulk_density,
    validate_dbh_cm,
    validate_height_m,
    validate_wood_density,
    validate_year,
)
from .enums import CalculationMode, EstimationType, OperationalEmissionSource
from .vegetation import VegetationDescription


class BiomassObservation(BaseModel):
    """Observação de biomassa seca de um pool.

    Informar ``dry_biomass_t`` (total) OU ``dry_biomass_t_ha`` (densidade).
    """

    dry_biomass_t: Optional[float] = Field(default=None, ge=0)
    dry_biomass_t_ha: Optional[float] = Field(default=None, ge=0)
    carbon_t: Optional[float] = Field(default=None, ge=0)
    estimation_type: EstimationType = EstimationType.MEASURED
    source: Optional[str] = None
    uncertainty_percent: Optional[float] = Field(default=None, ge=0, le=100)

    @model_validator(mode="after")
    def _exclusive(self) -> "BiomassObservation":
        provided = [
            v for v in (self.dry_biomass_t, self.dry_biomass_t_ha, self.carbon_t) if v is not None
        ]
        if len(provided) > 1:
            raise ValueError(
                "Informe apenas um entre dry_biomass_t, dry_biomass_t_ha e carbon_t"
            )
        return self

    @property
    def is_empty(self) -> bool:
        return self.dry_biomass_t is None and self.dry_biomass_t_ha is None and self.carbon_t is None


class BelowgroundObservation(BiomassObservation):
    """BGB medida, ou razão raiz:parte aérea específica do projeto.

    Se ``root_to_shoot_ratio`` for informado, ele entra na hierarquia de dados
    como ``project_specific`` e tem precedência sobre defaults IPCC.
    """

    root_to_shoot_ratio: Optional[float] = Field(default=None, gt=0, le=5)
    root_to_shoot_source: Optional[str] = None
    #: Incerteza DA RAZÃO (distinta da incerteza da medição de BGB).
    root_to_shoot_uncertainty_percent: Optional[float] = Field(default=None, ge=0, le=100)


class SoilObservation(BaseModel):
    """Medição de carbono orgânico do solo.

    ``area_ha`` é opcional: quando ausente, usa-se a área do projeto.
    """

    depth_cm: float = Field(gt=0, le=300)
    bulk_density_g_cm3: float
    organic_carbon_percent: float = Field(gt=0, le=100)
    coarse_fragment_fraction: float = Field(default=0.0, ge=0, lt=1)
    area_ha: Optional[float] = Field(default=None, gt=0)
    sample_count: Optional[int] = Field(default=None, ge=1)
    estimation_type: EstimationType = EstimationType.MEASURED
    source: Optional[str] = None
    uncertainty_percent: Optional[float] = Field(default=None, ge=0, le=100)

    @model_validator(mode="after")
    def _check(self) -> "SoilObservation":
        validate_bulk_density(self.bulk_density_g_cm3)
        return self


class TreeMeasurement(BaseModel):
    tree_id: Optional[str] = None
    species: Optional[str] = None
    dbh_cm: float
    height_m: Optional[float] = None
    wood_density_g_cm3: Optional[float] = None
    equation_id: Optional[str] = None
    alive: bool = True

    @model_validator(mode="after")
    def _check(self) -> "TreeMeasurement":
        validate_dbh_cm(self.dbh_cm)
        validate_height_m(self.height_m)
        validate_wood_density(self.wood_density_g_cm3)
        return self


class Plot(BaseModel):
    plot_id: str
    area_m2: float = Field(gt=0)
    trees: list[TreeMeasurement] = Field(default_factory=list)
    #: Fator de expansão explícito. Se ausente, o motor extrapola pela razão
    #: área do projeto / área amostrada e registra isso como ``modelled``.
    expansion_factor: Optional[float] = Field(default=None, gt=0)


class OperationalEmissionEntry(BaseModel):
    """Emissão operacional (NÃO biogênica).

    Informe ``emission_tCO2e`` diretamente, ou ``activity_amount`` + unidade
    para resolução via fator (que hoje está pendente de validação).
    """

    source: OperationalEmissionSource
    #: Ano da atividade. Fatores como o da rede elétrica variam por ano e o
    #: motor NÃO extrapola de um ano para outro.
    year: Optional[int] = None
    country: Optional[str] = None
    activity_amount: Optional[float] = Field(default=None, ge=0)
    activity_unit: Optional[str] = None
    emission_tCO2e: Optional[float] = Field(default=None, ge=0)
    factor_id: Optional[str] = None
    description: Optional[str] = None


class CarbonInventory(BaseModel):
    """Um inventário = um instantâneo temporal do projeto.

    Nunca sobrescrever: cada ``inventory_id`` é imutável e a série temporal é
    comparável.
    """

    inventory_id: str
    project_id: str
    year: int
    mode: CalculationMode = CalculationMode.INVENTORY
    aboveground: Optional[BiomassObservation] = None
    belowground: Optional[BelowgroundObservation] = None
    deadwood: Optional[BiomassObservation] = None
    litter: Optional[BiomassObservation] = None
    soil: Optional[SoilObservation] = None
    plots: list[Plot] = Field(default_factory=list)
    vegetation: Optional[VegetationDescription] = None
    carbon_fraction_override: Optional[float] = Field(default=None, gt=0, le=1)
    carbon_fraction_source: Optional[str] = None
    notes: Optional[str] = None
    #: Emenda: id do inventário substituído. O anterior permanece no histórico.
    supersedes: Optional[str] = None
    revision: int = 1
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def _check(self) -> "CarbonInventory":
        validate_year(self.year, "year")
        return self
