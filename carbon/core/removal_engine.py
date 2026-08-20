"""Anualização da mudança de estoque, perdas e balanço líquido.

Distinções mantidas:

* estoque  != remoção;
* remoção  != crédito;
* carbono biogênico != emissão operacional.
"""

from __future__ import annotations

from typing import Optional, Sequence

from ..models.enums import ResultStatus
from ..models.land import LandEvent
from ..models.inventory import OperationalEmissionEntry
from ..models.result import (
    LossResult,
    NetBalanceResult,
    OperationalEmissionsResult,
    RemovalResult,
    StockChangeResult,
)
from ..factors.emission_factors import CATEGORY as EF_CATEGORY
from ..services.factor_service import FactorService
from ..utils.conversions import carbon_to_co2e


def compute_removal(change: StockChangeResult, *, area_ha: Optional[float] = None) -> RemovalResult:
    """Anualização linear: ΔC / t.

    A anualização linear assume taxa constante no período. Para séries com
    mais de dois pontos, usar a série completa (P2).
    """
    if change.delta_carbon_t is None:
        return RemovalResult(
            period_years=change.period_years,
            notes=["Mudança de estoque indisponível: remoção não calculável."],
        )

    delta_c = change.delta_carbon_t
    delta_co2 = carbon_to_co2e(delta_c)
    annual_c = delta_c / change.period_years
    annual_co2 = carbon_to_co2e(annual_c)

    notes = ["Anualização linear assume taxa constante entre T0 e T1."]
    if delta_c < 0:
        notes.append(
            "ΔC negativo: houve PERDA líquida de estoque no período. "
            "O valor anual NÃO representa remoção."
        )

    return RemovalResult(
        period_years=change.period_years,
        carbon_stock_change_tC=delta_c,
        co2_stock_change_tCO2e=delta_co2,
        annual_carbon_change_tC=annual_c,
        annual_co2_removal_tCO2e_year=annual_co2,
        annual_co2_removal_tCO2e_ha_year=(annual_co2 / area_ha) if area_ha else None,
        is_removal=delta_c > 0,
        notes=notes,
    )


def compute_losses(events: Sequence[LandEvent]) -> LossResult:
    """Agrega perdas quantificadas. Eventos sem quantificação são contados,
    nunca estimados a partir do tipo."""
    quantified = [e for e in events if e.carbon_loss_tC is not None]
    unquantified = [e for e in events if e.carbon_loss_tC is None]

    total_c = sum(e.carbon_loss_tC for e in quantified) if quantified else None  # type: ignore[misc]
    return LossResult(
        total_carbon_loss_tC=total_c,
        total_co2e_loss_tCO2e=carbon_to_co2e(total_c) if total_c is not None else None,
        quantified_events=len(quantified),
        unquantified_events=len(unquantified),
        events=[
            {
                "event_type": e.event_type.value,
                "date": e.date.isoformat(),
                "affected_area_ha": e.affected_area_ha,
                "carbon_loss_tC": e.carbon_loss_tC,
                "quantified": e.carbon_loss_tC is not None,
                "estimation_type": e.estimation_type.value,
            }
            for e in events
        ],
    )


def compute_operational_emissions(
    entries: Sequence[OperationalEmissionEntry], factor_service: FactorService
) -> OperationalEmissionsResult:
    resolved: list[dict] = []
    unresolved: list[dict] = []
    notes: list[str] = []

    for entry in entries:
        if entry.emission_tCO2e is not None:
            resolved.append(
                {
                    "source": entry.source.value,
                    "emission_tCO2e": entry.emission_tCO2e,
                    "basis": "informado_diretamente",
                }
            )
            continue

        # Resolve pela FONTE DA ATIVIDADE e pelo ANO — nunca por categoria solta,
        # que faria diesel usar o fator da eletricidade.
        factor = factor_service.try_resolve(
            EF_CATEGORY,
            purpose=f"operational emission ({entry.source.value})",
            level=entry.source.value,
            year=entry.year,
            country=entry.country,
        )
        if factor is None or entry.activity_amount is None:
            unresolved.append(
                {
                    "source": entry.source.value,
                    "year": entry.year,
                    "activity_amount": entry.activity_amount,
                    "activity_unit": entry.activity_unit,
                    "reason": (
                        "fator de emissão não disponível para esta fonte/ano, ou atividade "
                        "não informada"
                    ),
                }
            )
            continue

        emission = entry.activity_amount * factor.value
        record = {
            "source": entry.source.value,
            "year": entry.year,
            "emission_t": emission,
            "gas": factor.gas,
            "factor_id": factor.factor_id,
            "factor_unit": factor.unit,
            "basis": "atividade x fator",
        }
        if factor.gas == "CO2":
            # CO2 é o próprio índice: tCO2 = tCO2e sem aplicar GWP.
            record["emission_tCO2e"] = emission
            record["gwp_version"] = None
            record["completeness"] = (
                "APENAS CO2 — não inclui CH4 nem N2O desta fonte. Subestima o total."
            )
        else:
            record["emission_tCO2e"] = None
            record["completeness"] = (
                f"Fator em {factor.gas}: conversão para CO2e exige GWP declarado "
                f"(ver core/gwp.py). Não convertido."
            )
            unresolved.append(record)
            continue
        resolved.append(record)

    total = sum(r["emission_tCO2e"] for r in resolved) if resolved else None
    if unresolved:
        notes.append(
            f"{len(unresolved)} lançamento(s) operacional(is) sem fator de emissão "
            "utilizável. Não foram estimados nem zerados."
        )
    return OperationalEmissionsResult(
        total_tCO2e=total,
        resolved_entries=len(resolved),
        unresolved_entries=len(unresolved),
        entries=resolved + unresolved,
        notes=notes,
    )


def compute_net_balance(
    removal: Optional[RemovalResult],
    losses: Optional[LossResult],
    operational: Optional[OperationalEmissionsResult],
) -> NetBalanceResult:
    """Net = Remoções brutas - Perdas - Emissões operacionais.

    Componentes ausentes não são zerados: entram em ``excluded_components`` e o
    status vira ``partial``.
    """
    excluded: list[str] = []
    notes: list[str] = []

    gross = removal.co2_stock_change_tCO2e if removal else None
    if gross is None:
        excluded.append("gross_removals")

    loss = losses.total_co2e_loss_tCO2e if losses else None
    if losses and losses.unquantified_events:
        notes.append(
            f"{losses.unquantified_events} evento(s) de perda registrado(s) sem quantificação."
        )
    if losses is None or loss is None:
        if losses is not None and losses.events:
            excluded.append("carbon_losses")

    ops = operational.total_tCO2e if operational else None
    if operational is not None and operational.unresolved_entries:
        excluded.append("operational_emissions_partial")

    if gross is None:
        return NetBalanceResult(
            gross_removals_tCO2e=None,
            carbon_losses_tCO2e=loss,
            operational_emissions_tCO2e=ops,
            net_balance_tCO2e=None,
            status=ResultStatus.PARTIAL,
            excluded_components=excluded,
            notes=notes + ["Balanço líquido não calculável sem mudança de estoque."],
        )

    net = gross - (loss or 0.0) - (ops or 0.0)
    if loss is None and losses is not None and losses.events:
        notes.append("Perdas presentes mas não quantificadas — não subtraídas do balanço.")
    if ops is None:
        notes.append("Emissões operacionais não informadas — não subtraídas do balanço.")
    else:
        notes.append(
            "Emissões operacionais são contabilizadas separadamente do estoque biogênico."
        )

    return NetBalanceResult(
        gross_removals_tCO2e=gross,
        carbon_losses_tCO2e=loss,
        operational_emissions_tCO2e=ops,
        net_balance_tCO2e=net,
        status=ResultStatus.COMPLETE if not excluded else ResultStatus.PARTIAL,
        excluded_components=excluded,
        notes=notes,
    )
