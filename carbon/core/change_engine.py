"""Mudança de estoque entre dois inventários (T0 -> T1).

Regra central: só entram no delta os pools disponíveis NOS DOIS períodos. Um
pool medido apenas em um período não pode ser comparado — tratá-lo como zero
no outro produziria remoção ou perda fictícia.
"""

from __future__ import annotations

from ..models.enums import ResultStatus
from ..models.result import CarbonStockResult, PoolChange, StockChangeResult
from ..utils.conversions import carbon_to_co2e
from ..utils.validation import validate_period


def compute_stock_change(
    baseline: CarbonStockResult,
    current: CarbonStockResult,
    *,
    baseline_year: int,
    current_year: int,
) -> StockChangeResult:
    period = validate_period(baseline_year, current_year)

    comparable: list[str] = []
    non_comparable: list[PoolChange] = []
    pool_changes: list[PoolChange] = []
    notes: list[str] = []

    all_pools = sorted(set(baseline.pools) | set(current.pools))
    for pool in all_pools:
        b = baseline.pools.get(pool)
        c = current.pools.get(pool)
        b_val = b.carbon_t.value if b and b.carbon_t.available else None
        c_val = c.carbon_t.value if c and c.carbon_t.available else None

        if b_val is not None and c_val is not None:
            change = PoolChange(
                pool=pool,
                baseline_carbon_t=b_val,
                current_carbon_t=c_val,
                delta_carbon_t=c_val - b_val,
                comparable=True,
            )
            comparable.append(pool)
            pool_changes.append(change)
        else:
            reason = (
                "pool ausente no baseline"
                if b_val is None and c_val is not None
                else "pool ausente no inventário atual"
                if c_val is None and b_val is not None
                else "pool ausente nos dois períodos"
            )
            change = PoolChange(
                pool=pool,
                baseline_carbon_t=b_val,
                current_carbon_t=c_val,
                delta_carbon_t=None,
                comparable=False,
                reason=f"{reason} — excluído do delta (não pode ser tratado como zero)",
            )
            non_comparable.append(change)
            pool_changes.append(change)

    if not comparable:
        return StockChangeResult(
            baseline_year=baseline_year,
            current_year=current_year,
            period_years=period,
            comparable_pools=[],
            non_comparable_pools=non_comparable,
            pool_changes=pool_changes,
            status=ResultStatus.FAILED,
            notes=["Nenhum pool comparável entre os dois inventários."],
        )

    b_total = sum(p.baseline_carbon_t for p in pool_changes if p.comparable)  # type: ignore[misc]
    c_total = sum(p.current_carbon_t for p in pool_changes if p.comparable)  # type: ignore[misc]
    delta = c_total - b_total

    if non_comparable:
        notes.append(
            "Delta calculado apenas sobre pools comparáveis: "
            + ", ".join(comparable)
            + ". Pools excluídos: "
            + ", ".join(p.pool for p in non_comparable)
        )

    return StockChangeResult(
        baseline_year=baseline_year,
        current_year=current_year,
        period_years=period,
        comparable_pools=comparable,
        non_comparable_pools=non_comparable,
        pool_changes=pool_changes,
        baseline_comparable_carbon_t=b_total,
        current_comparable_carbon_t=c_total,
        delta_carbon_t=delta,
        delta_co2e_t=carbon_to_co2e(delta),
        direction="increase" if delta > 0 else "decrease" if delta < 0 else "stable",
        status=ResultStatus.COMPLETE if not non_comparable else ResultStatus.PARTIAL,
        notes=notes,
    )
