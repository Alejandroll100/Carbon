"""Conjuntos de GWP (Global Warming Potential).

Regra: NUNCA misturar AR4, AR5 e AR6 silenciosamente. Todo cálculo que produz
CO2e declara ``gwp_version``, e o motor recusa combinar versões diferentes
dentro do mesmo resultado.

Os valores abaixo NÃO foram transcritos de fonte primária nesta rodada: o
registro está estruturado e vazio de propósito. Preencher exige o relatório de
avaliação do IPCC correspondente (AR4 Tabela 2.14, AR5 Apêndice 8.A, AR6
Tabela 7.15) e o horizonte temporal declarado (100 anos, por convenção da
UNFCCC).
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class GWPNotAvailableError(LookupError):
    """GWP não cadastrado para o gás/versão solicitados."""


class GWPMixingError(RuntimeError):
    """Tentativa de combinar versões de GWP diferentes no mesmo resultado."""


class GWPSet(BaseModel):
    version: str
    time_horizon_years: int = 100
    reference_id: Optional[str] = None
    page_or_table: Optional[str] = None
    #: gás -> GWP. Vazio = pendente de transcrição da fonte primária.
    values: dict[str, float] = {}
    notes: Optional[str] = None

    def get(self, gas: str) -> float:
        if gas == "CO2":
            return 1.0  # definição do índice, não valor empírico
        try:
            return self.values[gas]
        except KeyError as exc:
            raise GWPNotAvailableError(
                f"GWP de {gas} não cadastrado no conjunto {self.version}. "
                f"Transcrever da fonte primária antes de usar."
            ) from exc


GWP_SETS: dict[str, GWPSet] = {
    "AR4": GWPSet(
        version="AR4",
        reference_id=None,
        page_or_table="IPCC AR4 (2007), WG1, Tabela 2.14",
        values={},
        notes="PENDENTE de transcrição.",
    ),
    "AR5": GWPSet(
        version="AR5",
        reference_id=None,
        page_or_table="IPCC AR5 (2013), WG1, Apêndice 8.A",
        values={},
        notes="PENDENTE de transcrição.",
    ),
    "AR6": GWPSet(
        version="AR6",
        reference_id=None,
        page_or_table="IPCC AR6 (2021), WG1, Tabela 7.15",
        values={},
        notes="PENDENTE de transcrição.",
    ),
}

DEFAULT_GWP_VERSION = "AR6"


def get_gwp_set(version: str = DEFAULT_GWP_VERSION) -> GWPSet:
    try:
        return GWP_SETS[version]
    except KeyError as exc:
        raise GWPNotAvailableError(
            f"Conjunto de GWP desconhecido: {version}. Disponíveis: {sorted(GWP_SETS)}"
        ) from exc


def to_co2e(mass_t: float, gas: str, *, version: str = DEFAULT_GWP_VERSION) -> tuple[float, str]:
    """Converte massa de um gás em tCO2e. Devolve (valor, versão de GWP usada)."""
    gwp = get_gwp_set(version).get(gas)
    return mass_t * gwp, version


def assert_single_gwp_version(versions: list[str]) -> Optional[str]:
    distinct = {v for v in versions if v}
    if len(distinct) > 1:
        raise GWPMixingError(
            f"Resultado combinaria versões de GWP diferentes: {sorted(distinct)}. "
            f"Recalcule tudo com uma única versão."
        )
    return distinct.pop() if distinct else None
