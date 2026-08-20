"""Descrição da vegetação, incluindo componentes de SAF (multiespécie)."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from .enums import ComponentType


class VegetationComponent(BaseModel):
    """Um estrato/componente do sistema. Um SAF tem vários."""

    type: ComponentType
    species: Optional[str] = None
    count: Optional[int] = Field(default=None, ge=0)
    density_per_ha: Optional[float] = Field(default=None, gt=0)
    planting_year: Optional[int] = None
    spacing_m: Optional[str] = None
    notes: Optional[str] = None


class VegetationDescription(BaseModel):
    components: list[VegetationComponent] = Field(default_factory=list)
    vegetation_type: Optional[str] = None
    age_years: Optional[float] = Field(default=None, ge=0)

    @property
    def species_list(self) -> list[str]:
        return [c.species for c in self.components if c.species]
