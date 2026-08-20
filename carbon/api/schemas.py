"""Schemas de request/response da API de carbono.

Os modelos de domínio (``models/``) são a fonte de verdade. Aqui só existe o
que é específico do transporte HTTP.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from ..models.enums import CalculationMode, LandUse
from ..models.inventory import (
    BelowgroundObservation,
    BiomassObservation,
    OperationalEmissionEntry,
    Plot,
    SoilObservation,
    TreeMeasurement,
)
from ..models.land import LandEvent
from ..models.project import Coordinates, Geometry
from ..models.vegetation import VegetationDescription
from ..services.factor_service import ProjectParameter
from ..services.geospatial_analysis import GeospatialAnalysisInput

#: Entrada do endpoint geoespacial. O schema de domínio é a fonte de verdade;
#: o transporte apenas o reexporta.
GeospatialAnalyzeRequest = GeospatialAnalysisInput


class CreateProjectRequest(BaseModel):
    project_id: Optional[str] = None
    name: str
    country: Optional[str] = None
    state: Optional[str] = None
    municipality: Optional[str] = None
    land_use: LandUse
    area_ha: float = Field(gt=0)
    coordinates: Coordinates
    geometry: Optional[Geometry] = None
    reference_year: int
    baseline_year: Optional[int] = None
    climate_domain: Optional[str] = None
    biome: Optional[str] = None
    region: Optional[str] = None
    soil_type: Optional[str] = None


class CreateInventoryRequest(BaseModel):
    inventory_id: Optional[str] = None
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


class SoilMeasurementRequest(BaseModel):
    """Anexa medição de solo a um inventário, criando NOVA revisão."""

    inventory_id: str
    soil: SoilObservation


class TreeMeasurementRequest(BaseModel):
    """Anexa parcelas/árvores a um inventário, criando NOVA revisão."""

    inventory_id: str
    plots: list[Plot] = Field(default_factory=list)
    trees: list[TreeMeasurement] = Field(default_factory=list)
    #: Usado quando ``trees`` é enviado sem estrutura de parcela.
    plot_id: Optional[str] = None
    plot_area_m2: Optional[float] = Field(default=None, gt=0)


class CalculateRequest(BaseModel):
    inventory_id: str
    baseline_inventory_id: Optional[str] = None
    mode: Optional[CalculationMode] = None
    events: list[LandEvent] = Field(default_factory=list)
    operational_emissions: list[OperationalEmissionEntry] = Field(default_factory=list)
    #: Parâmetros específicos do projeto por categoria de fator
    #: (ex.: {"root_to_shoot_ratio": {"value": 0.24, "unit": "t BGB / t AGB", ...}}).
    project_parameters: dict[str, ProjectParameter] = Field(default_factory=dict)
    #: Se True, recusa fatores REQUIRES_VALIDATION em vez de apenas alertar.
    strict_factor_validation: bool = False
    use_stored_events: bool = True


class EventRequest(BaseModel):
    event: LandEvent


class EmissionRequest(BaseModel):
    entry: OperationalEmissionEntry


class ErrorResponse(BaseModel):
    error: str
    detail: str
    hint: Optional[str] = None
