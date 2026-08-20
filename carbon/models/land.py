"""Parcelas e eventos de mudança de uso/perda de carbono."""

from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field

from .enums import EstimationType, EventType, LandUse


class LandParcel(BaseModel):
    parcel_id: str
    project_id: str
    area_ha: float = Field(gt=0)
    land_use: LandUse
    description: Optional[str] = None


class LandEvent(BaseModel):
    """Evento de perda/distúrbio.

    ``carbon_loss_tC`` só é preenchido quando há base para quantificar. O motor
    NÃO estima perda a partir do tipo de evento sem dado — registra o evento e
    marca o resultado como parcial.
    """

    event_id: Optional[str] = None
    event_type: EventType
    date: date
    affected_area_ha: float = Field(gt=0)
    carbon_loss_tC: Optional[float] = Field(default=None, ge=0)
    estimation_type: EstimationType = EstimationType.NOT_AVAILABLE
    source: Optional[str] = None
    description: Optional[str] = None
