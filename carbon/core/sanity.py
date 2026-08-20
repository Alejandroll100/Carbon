"""Verificações científicas de plausibilidade.

Distinção deliberada:

* **erro** — fisicamente impossível. Já é barrado na validação de entrada
  (``utils/validation.py``) e aqui vira ``severity="error"``.
* **aviso** — raro, suspeito, mas possível. NUNCA rejeita o resultado. Um
  estoque alto pode ser real; cabe ao analista decidir.

Nenhum limiar abaixo é um fator científico: são faixas de plausibilidade
operacionais da GEØ.IA, documentadas como tal, e por isso vivem aqui e não na
base de fatores.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:  # pragma: no cover
    from ..models.result import CarbonResult

#: Limiares de plausibilidade (GEØ.IA, não IPCC).
MAX_PLAUSIBLE_CARBON_T_HA = 700.0
MAX_PLAUSIBLE_SOC_T_HA = 400.0
MAX_PLAUSIBLE_ANNUAL_REMOVAL_TCO2E_HA = 50.0
MAX_PLAUSIBLE_ROOT_SHOOT = 1.5


class SanityFinding(BaseModel):
    code: str
    severity: str  # "error" | "warning" | "info"
    message: str
    value: float | None = None
    threshold: float | None = None


def run_sanity_checks(result: "CarbonResult") -> list[SanityFinding]:
    findings: list[SanityFinding] = []
    stock = result.carbon_stock

    if stock is not None:
        for name, pool in stock.pools.items():
            value = pool.carbon_t.value
            if value is None:
                continue
            if value < 0:
                findings.append(
                    SanityFinding(
                        code="negative_pool_carbon",
                        severity="error",
                        message=f"Pool {name} com carbono negativo: fisicamente impossível.",
                        value=value,
                    )
                )
            per_ha = pool.carbon_t_ha
            if per_ha is None:
                continue
            limit = MAX_PLAUSIBLE_SOC_T_HA if name == "soil_organic_carbon" else MAX_PLAUSIBLE_CARBON_T_HA
            if per_ha > limit:
                findings.append(
                    SanityFinding(
                        code="implausible_pool_density",
                        severity="warning",
                        message=(
                            f"Pool {name} em {per_ha:.1f} tC/ha excede a faixa usual "
                            f"(> {limit:.0f}). Pode ser real — conferir área, unidade e fator."
                        ),
                        value=per_ha,
                        threshold=limit,
                    )
                )

        if stock.total_carbon_t is not None and stock.area_ha <= 0:
            findings.append(
                SanityFinding(
                    code="area_stock_mismatch",
                    severity="error",
                    message="Estoque calculado com área não positiva.",
                )
            )

        declared = set(stock.pools)
        if len(declared) != len(stock.pools):
            findings.append(
                SanityFinding(code="duplicate_pool", severity="error", message="Pool duplicado.")
            )

    removal = result.removal
    if removal and removal.annual_co2_removal_tCO2e_ha_year is not None:
        rate = abs(removal.annual_co2_removal_tCO2e_ha_year)
        if rate > MAX_PLAUSIBLE_ANNUAL_REMOVAL_TCO2E_HA:
            findings.append(
                SanityFinding(
                    code="implausible_removal_rate",
                    severity="warning",
                    message=(
                        f"Taxa anual de {rate:.1f} tCO2e/ha/ano excede a faixa usual "
                        f"(> {MAX_PLAUSIBLE_ANNUAL_REMOVAL_TCO2E_HA:.0f}). Conferir intervalo "
                        f"entre inventários e comparabilidade dos pools."
                    ),
                    value=rate,
                    threshold=MAX_PLAUSIBLE_ANNUAL_REMOVAL_TCO2E_HA,
                )
            )

    if stock is not None:
        agb = stock.pools.get("aboveground_biomass")
        bgb = stock.pools.get("belowground_biomass")
        if agb and bgb and agb.carbon_t.value and bgb.carbon_t.value:
            ratio = bgb.carbon_t.value / agb.carbon_t.value
            if ratio > MAX_PLAUSIBLE_ROOT_SHOOT:
                findings.append(
                    SanityFinding(
                        code="implausible_root_shoot",
                        severity="warning",
                        message=(
                            f"Razão BGB/AGB de {ratio:.2f} excede a faixa usual de sistemas "
                            f"lenhosos (> {MAX_PLAUSIBLE_ROOT_SHOOT}). Plausível em pastagem, "
                            f"suspeito em floresta ou SAF."
                        ),
                        value=ratio,
                        threshold=MAX_PLAUSIBLE_ROOT_SHOOT,
                    )
                )

    if result.change and result.change.period_years and result.change.period_years > 20:
        findings.append(
            SanityFinding(
                code="long_inventory_interval",
                severity="warning",
                message=(
                    f"Intervalo de {result.change.period_years} anos entre inventários: a "
                    f"anualização linear perde significado em séries longas."
                ),
                value=float(result.change.period_years),
            )
        )
    return findings
