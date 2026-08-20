"""Insights estruturados e determinísticos.

Nenhum LLM participa do cálculo. Estes insights são derivados por regra a
partir do resultado já computado. Um LLM pode, no futuro, apenas redigir a
interpretação — nunca produzir o número.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..models.result import Insight

if TYPE_CHECKING:  # pragma: no cover
    from ..models.result import CarbonResult


def build_insights(result: "CarbonResult") -> list[Insight]:
    insights: list[Insight] = []
    stock = result.carbon_stock

    if stock and stock.total_carbon_t and stock.available_pools:
        dominant = max(
            stock.available_pools, key=lambda n: stock.pools[n].carbon_t.value or 0.0
        )
        share = (stock.pools[dominant].carbon_t.value or 0.0) / stock.total_carbon_t * 100.0
        insights.append(
            Insight(
                type="dominant_pool",
                message=(
                    f"{dominant} representa {share:.1f}% do estoque de carbono MEDIDO "
                    f"(pools disponíveis: {', '.join(stock.available_pools)})."
                ),
            )
        )

    if stock and stock.missing_pools:
        insights.append(
            Insight(
                type="data_gap",
                message=(
                    "Pools não contabilizados: "
                    + ", ".join(stock.missing_pools)
                    + ". O total NÃO representa o estoque completo da área."
                ),
                severity="warning",
            )
        )

    if stock:
        defaults = [
            n
            for n in stock.available_pools
            if stock.pools[n].carbon_t.estimation_type.value == "default_factor"
        ]
        if defaults:
            insights.append(
                Insight(
                    type="tier1_dependency",
                    message="Pools dependentes de fator default (Tier 1): " + ", ".join(defaults),
                    severity="warning",
                )
            )

    if result.change and result.change.non_comparable_pools:
        insights.append(
            Insight(
                type="comparability",
                message=(
                    "Pools excluídos do delta por não existirem nos dois períodos: "
                    + ", ".join(p.pool for p in result.change.non_comparable_pools)
                ),
                severity="warning",
            )
        )

    if result.removal and result.removal.carbon_stock_change_tC is not None:
        if result.removal.is_removal:
            insights.append(
                Insight(
                    type="stock_trend",
                    message=(
                        f"Aumento de estoque de {result.removal.carbon_stock_change_tC:.2f} tC "
                        f"em {result.removal.period_years} ano(s). Estimativa de remoção, "
                        "não crédito de carbono."
                    ),
                )
            )
        else:
            insights.append(
                Insight(
                    type="stock_trend",
                    message=(
                        f"Perda líquida de {abs(result.removal.carbon_stock_change_tC):.2f} tC "
                        f"em {result.removal.period_years} ano(s)."
                    ),
                    severity="alert",
                )
            )

    if stock and not stock.uncertainty.available:
        insights.append(
            Insight(
                type="uncertainty",
                message=(
                    "Intervalo de incerteza não calculado. "
                    + (stock.uncertainty.reason or "")
                ),
                severity="warning",
            )
        )

    if result.validation_warnings:
        insights.append(
            Insight(
                type="factor_validation",
                message=(
                    f"{len(result.validation_warnings)} fator(es)/equação(ões) em estado "
                    "REQUIRES_VALIDATION foram utilizados. Resultado provisório."
                ),
                severity="alert",
            )
        )

    if result.operational_emissions and result.operational_emissions.unresolved_entries:
        insights.append(
            Insight(
                type="operational_emissions",
                message=(
                    f"{result.operational_emissions.unresolved_entries} lançamento(s) "
                    "operacional(is) sem fator de emissão validado — não incluídos no balanço."
                ),
                severity="warning",
            )
        )

    return insights
