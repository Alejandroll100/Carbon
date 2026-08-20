"""Valor rastreável: todo número do motor carrega sua origem.

Regra §45: qualquer número deve responder de onde veio, qual dado entrou,
qual equação, qual fator, qual unidade, qual fonte, qual confiança e qual
versão do motor calculou.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from .enums import DataLevel, EstimationType


class TracedValue(BaseModel):
    """Valor numérico + proveniência completa.

    ``value is None`` significa NÃO DISPONÍVEL. Nunca é interpretado como zero
    em nenhum agregador do motor.
    """

    value: Optional[float] = None
    unit: str
    estimation_type: EstimationType = EstimationType.NOT_AVAILABLE
    data_level: Optional[DataLevel] = None
    source: Optional[str] = None
    tier: Optional[int] = None
    uncertainty_percent: Optional[float] = None
    factors_used: list[str] = Field(default_factory=list)
    equations_used: list[str] = Field(default_factory=list)
    inputs: dict[str, float | str | None] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)

    @property
    def available(self) -> bool:
        return self.value is not None

    @classmethod
    def not_available(cls, unit: str, reason: str) -> "TracedValue":
        return cls(
            value=None,
            unit=unit,
            estimation_type=EstimationType.NOT_AVAILABLE,
            notes=[reason],
        )


class UncertaintyRange(BaseModel):
    """Intervalo de incerteza. Se não for calculável, ``available=False``.

    Nunca inventar intervalo.
    """

    available: bool = False
    estimate: Optional[float] = None
    lower_bound: Optional[float] = None
    upper_bound: Optional[float] = None
    uncertainty_percent: Optional[float] = None
    method: Optional[str] = None
    reason: Optional[str] = None
