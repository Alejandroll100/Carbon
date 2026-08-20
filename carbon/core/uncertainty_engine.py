"""Propagação de incerteza (IPCC Approach 1).

Soma/subtração de termos independentes:

    U_total = sqrt( sum( (U_i * x_i)^2 ) ) / | sum(x_i) |

Produto de termos independentes:

    U_total = sqrt( sum( U_i^2 ) )

Se qualquer componente não tiver incerteza declarada, o resultado NÃO recebe
intervalo: ``available=False`` com motivo explícito. Nunca inventar intervalo.
"""

from __future__ import annotations

import math
from typing import Iterable, Optional

from ..models.provenance import UncertaintyRange

APPROACH_1_SUM = "IPCC Approach 1 — propagação por soma em quadratura"
APPROACH_1_PRODUCT = "IPCC Approach 1 — propagação por produto em quadratura"


def combine_sum(
    components: Iterable[tuple[str, float, Optional[float]]],
) -> UncertaintyRange:
    """``components``: (nome, valor, uncertainty_percent)."""
    items = list(components)
    if not items:
        return UncertaintyRange(available=False, reason="Nenhum componente informado.")

    missing = [name for name, _, unc in items if unc is None]
    if missing:
        return UncertaintyRange(
            available=False,
            reason=(
                "Incerteza não calculável: componentes sem incerteza declarada: "
                + ", ".join(sorted(missing))
            ),
        )

    total = sum(value for _, value, _ in items)
    if total == 0:
        return UncertaintyRange(available=False, reason="Soma nula: incerteza relativa indefinida.")

    abs_sq = sum(((unc / 100.0) * value) ** 2 for _, value, unc in items)  # type: ignore[operator]
    abs_unc = math.sqrt(abs_sq)
    pct = abs_unc / abs(total) * 100.0
    return UncertaintyRange(
        available=True,
        estimate=total,
        lower_bound=total - abs_unc,
        upper_bound=total + abs_unc,
        uncertainty_percent=pct,
        method=APPROACH_1_SUM,
    )


def combine_product(
    value: float, uncertainties_percent: Iterable[Optional[float]], *, labels: Optional[list[str]] = None
) -> UncertaintyRange:
    uncs = list(uncertainties_percent)
    if any(u is None for u in uncs) or not uncs:
        return UncertaintyRange(
            available=False,
            reason="Incerteza não calculável: fator ou variável sem incerteza declarada.",
        )
    pct = math.sqrt(sum(u**2 for u in uncs))  # type: ignore[operator]
    abs_unc = abs(value) * pct / 100.0
    return UncertaintyRange(
        available=True,
        estimate=value,
        lower_bound=value - abs_unc,
        upper_bound=value + abs_unc,
        uncertainty_percent=pct,
        method=APPROACH_1_PRODUCT,
    )
