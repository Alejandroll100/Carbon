"""Entidade Carbon Project e geometria mínima do MVP."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from ..utils.validation import validate_coordinates, validate_year
from .enums import (
    CarbonInputLevel,
    IPCCClimateRegion,
    IPCCSoilType,
    LandUse,
    TillageManagement,
)


class Coordinates(BaseModel):
    lat: float
    lon: float

    @model_validator(mode="after")
    def _check(self) -> "Coordinates":
        validate_coordinates(self.lat, self.lon)
        return self


class Geometry(BaseModel):
    """Placeholder de geometria. No MVP, coordenada + área bastam.

    ``geometry_type`` prepara Point / Polygon / GeoJSON / Shapefile / KML sem
    implementar parsing agora (P2).
    """

    geometry_type: str = "point"
    reference: Optional[str] = None
    geojson: Optional[dict] = None

    @field_validator("geometry_type")
    @classmethod
    def _known(cls, v: str) -> str:
        allowed = {"point", "polygon", "geojson", "shapefile", "kml"}
        if v not in allowed:
            raise ValueError(f"geometry_type deve ser um de {sorted(allowed)}")
        return v


class CarbonProject(BaseModel):
    project_id: str
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
    # --- estratificação metodológica (entrada obrigatória para Tier 1) ---
    #: Região climática do IPCC (Tabela 2.3). NÃO é inferida de coordenadas.
    climate_region: Optional[IPCCClimateRegion] = None
    #: Classe de solo do IPCC (colunas da Tabela 2.3). Use
    #: ``soil_classification.to_ipcc_soil_type`` para converter do SiBCS.
    soil_type: Optional[IPCCSoilType] = None
    #: Classe de solo declarada pelo projeto antes da normalização (ex.: SiBCS).
    soil_type_source_classification: Optional[str] = None
    tillage: Optional[TillageManagement] = None
    carbon_input_level: Optional[CarbonInputLevel] = None
    #: Estratificação livre, usada como critério secundário de resolução.
    climate_domain: Optional[str] = None
    biome: Optional[str] = None
    region: Optional[str] = None
    ecological_zone: Optional[str] = None
    forest_type: Optional[str] = None
    continent: Optional[str] = None
    #: "natural" | "planted" — coluna Origin da Tabela 4.4 (2019).
    #: Espécie dominante em plantio homogêneo (Tabela 4.8 de 2019).
    species: Optional[str] = None
    forest_origin: Optional[str] = None
    #: "primary" | "secondary_over_20y" | "secondary_up_to_20y" (Tabela 4.7 de 2019).
    forest_status: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def _check_years(self) -> "CarbonProject":
        validate_year(self.reference_year, "reference_year")
        if self.baseline_year is not None:
            validate_year(self.baseline_year, "baseline_year")
        return self
