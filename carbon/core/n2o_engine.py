"""Emissões diretas de N2O por aplicação de nitrogênio.

Cadeia explícita, sem etapa escondida (IPCC 2006 Vol.4 Cap.11, Eq. 11.1):

    N aplicado [t N]
      x EF1                      -> N2O-N [t]
      x 44/28                    -> N2O   [t]
      x GWP(N2O, versão)         -> CO2e  [t]

O fator 44/28 é a razão de massa molar N2O/N2 — constante exata, não empírica.
EF1 e o GWP vêm da base de fatores e do conjunto de GWP declarado; enquanto
não estiverem preenchidos, o cálculo é recusado com a etapa exata que faltou.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from ..factors.registry import FactorNotFoundError
from ..services.factor_service import FactorResolver
from .gwp import DEFAULT_GWP_VERSION, GWPNotAvailableError, to_co2e

#: Razão de massa molar N2O (44,013) / N2 (28,014), arredondada para 44/28
#: conforme convenção IPCC. Constante exata.
N2O_N_TO_N2O_RATIO = 44.0 / 28.0


class N2OResult(BaseModel):
    n_applied_t: float
    ef1_kg_n2o_n_per_kg_n: Optional[float] = None
    n2o_n_t: Optional[float] = None
    n2o_t: Optional[float] = None
    co2e_t: Optional[float] = None
    gwp_version: Optional[str] = None
    factor_id: Optional[str] = None
    available: bool = False
    blocked_at: Optional[str] = None
    reason: Optional[str] = None
    steps: list[str] = []


def direct_n2o_from_nitrogen(
    n_applied_t: float,
    resolver: FactorResolver,
    *,
    gwp_version: str = DEFAULT_GWP_VERSION,
    country: Optional[str] = None,
) -> N2OResult:
    steps = [
        "N aplicado [t N]",
        "x EF1 [kg N2O-N / kg N]  -> N2O-N",
        f"x {N2O_N_TO_N2O_RATIO:.6f} (44/28)  -> N2O",
        f"x GWP(N2O, {gwp_version})  -> CO2e",
    ]
    ef1 = resolver.try_resolve(
        "operational_emission_factor",
        purpose="EF1 (N2O direto de N aplicado)",
        gas="N2O",
        level="fertilizer",
        country=country,
    )
    if ef1 is None:
        return N2OResult(
            n_applied_t=n_applied_t,
            blocked_at="EF1",
            reason=(
                "EF1 não disponível na base de fatores. Cadeia interrompida antes de N2O-N; "
                "nenhum valor foi estimado."
            ),
            steps=steps,
        )

    n2o_n_t = n_applied_t * ef1.value  # kg/kg == t/t
    n2o_t = n2o_n_t * N2O_N_TO_N2O_RATIO
    try:
        co2e_t, used_version = to_co2e(n2o_t, "N2O", version=gwp_version)
    except GWPNotAvailableError as exc:
        return N2OResult(
            n_applied_t=n_applied_t,
            ef1_kg_n2o_n_per_kg_n=ef1.value,
            n2o_n_t=n2o_n_t,
            n2o_t=n2o_t,
            factor_id=ef1.factor_id,
            blocked_at="GWP",
            reason=str(exc),
            steps=steps,
        )
    return N2OResult(
        n_applied_t=n_applied_t,
        ef1_kg_n2o_n_per_kg_n=ef1.value,
        n2o_n_t=n2o_n_t,
        n2o_t=n2o_t,
        co2e_t=co2e_t,
        gwp_version=used_version,
        factor_id=ef1.factor_id,
        available=True,
        steps=steps,
    )
