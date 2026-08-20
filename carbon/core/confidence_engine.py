"""Confidence Score e Data Quality Score (indicadores internos GEØ.IA).

IMPORTANTE: nenhum destes scores é certificação científica, probabilidade ou
substituto de análise de incerteza. São rubricas determinísticas de qualidade
e completude de dados, com pesos documentados e auditáveis.

Rubrica do Confidence Score (0-100):

    completude de pools ........ 25
    qualidade da medição ....... 25
    especificidade do fator .... 20
    tier metodológico .......... 15
    resolução temporal ......... 10
    status de validação ........  5

Teto: se qualquer fator REQUIRES_VALIDATION foi usado, o score é limitado a
``UNVALIDATED_FACTOR_CAP``. Dado provisório não produz confiança alta.
"""

from __future__ import annotations

from typing import Optional

from ..models.enums import ConfidenceClass, DataLevel, EstimationType, ValidationStatus
from ..models.result import CarbonStockResult, PoolResult, QualityResult, StockChangeResult
from ..services.factor_service import FactorService

WEIGHTS = {
    "pool_completeness": 25.0,
    "measurement_quality": 25.0,
    "factor_specificity": 20.0,
    "methodology_tier": 15.0,
    "temporal_resolution": 10.0,
    "validation_status": 5.0,
}

#: Peso relativo de cada pool na completude (soma 1.0).
POOL_WEIGHTS = {
    "aboveground_biomass": 0.35,
    "belowground_biomass": 0.20,
    "soil_organic_carbon": 0.30,
    "deadwood": 0.075,
    "litter": 0.075,
}

ESTIMATION_SCORE = {
    EstimationType.MEASURED: 1.00,
    EstimationType.MODELLED: 0.70,
    EstimationType.ESTIMATED: 0.60,
    EstimationType.REMOTE_SENSING: 0.60,
    EstimationType.DEFAULT_FACTOR: 0.30,
    EstimationType.NOT_AVAILABLE: 0.00,
}

DATA_LEVEL_SCORE = {
    DataLevel.MEASURED: 1.00,
    DataLevel.PROJECT_SPECIFIC: 0.85,
    DataLevel.REGIONAL: 0.70,
    DataLevel.NATIONAL: 0.55,
    DataLevel.IPCC_DEFAULT: 0.40,
}

TIER_SCORE = {3: 1.00, 2: 0.70, 1: 0.40}

UNVALIDATED_FACTOR_CAP = 70

#: Proxy é mais fraco que fator não validado do domínio correto.
PROXY_CAP = 55


def _classify(score: int) -> ConfidenceClass:
    if score <= 20:
        return ConfidenceClass.VERY_LOW
    if score <= 40:
        return ConfidenceClass.LOW
    if score <= 60:
        return ConfidenceClass.MEDIUM
    if score <= 80:
        return ConfidenceClass.HIGH
    return ConfidenceClass.VERY_HIGH


def _available_pools(stock: CarbonStockResult) -> list[PoolResult]:
    return [p for p in stock.pools.values() if p.available]


def compute_confidence(
    stock: CarbonStockResult,
    factor_service: FactorService,
    *,
    change: Optional[StockChangeResult] = None,
) -> QualityResult:
    drivers: list[str] = []
    penalties: list[str] = []
    available = _available_pools(stock)

    # 1. completude de pools
    completeness = sum(POOL_WEIGHTS.get(p.pool.value, 0.0) for p in available)
    for pool in stock.missing_pools:
        penalties.append(f"Pool ausente: {pool}")
    for p in available:
        drivers.append(f"Pool disponível: {p.pool.value} ({p.carbon_t.estimation_type.value})")

    # 2. qualidade da medição
    if available:
        measurement = sum(ESTIMATION_SCORE.get(p.carbon_t.estimation_type, 0.0) for p in available) / len(
            available
        )
    else:
        measurement = 0.0

    # 3. especificidade do fator
    if available:
        specificity = sum(
            DATA_LEVEL_SCORE.get(p.carbon_t.data_level or DataLevel.IPCC_DEFAULT, 0.4)
            for p in available
        ) / len(available)
    else:
        specificity = 0.0

    # 4. tier metodológico
    tiers = [p.carbon_t.tier or 1 for p in available]
    tier_component = sum(TIER_SCORE.get(t, 0.4) for t in tiers) / len(tiers) if tiers else 0.0
    max_tier = max(tiers) if tiers else 1

    # 5. resolução temporal
    if change is not None and change.comparable_pools:
        temporal = 1.0
        drivers.append(
            f"Série temporal comparável: {change.baseline_year}-{change.current_year} "
            f"({change.period_years} anos)"
        )
        if change.period_years > 10:
            temporal = 0.7
            penalties.append("Intervalo entre inventários maior que 10 anos")
        if change.non_comparable_pools:
            temporal = min(temporal, 0.6)
            penalties.append("Pools não comparáveis entre períodos")
    else:
        temporal = 0.4
        penalties.append("Sem inventário de baseline comparável")

    # 6. status de validação dos fatores usados
    used = factor_service.used
    if used:
        ok = [
            f
            for f in used
            if f.validation_status
            in (ValidationStatus.VALIDATED, ValidationStatus.EXACT_CONSTANT, ValidationStatus.PROJECT_SUPPLIED)
        ]
        validation = len(ok) / len(used)
        unvalidated = [f.factor_id for f in used if f.validation_status == ValidationStatus.REQUIRES_VALIDATION]
        if unvalidated:
            penalties.append(
                "Fatores REQUIRES_VALIDATION utilizados: " + ", ".join(sorted(set(unvalidated)))
            )
    else:
        validation = 1.0
        unvalidated = []

    proxies = [f.factor_id for f in used if f.proxy]
    if proxies:
        penalties.append("Fatores aplicados por PROXY: " + ", ".join(sorted(set(proxies))))

    raw = (
        completeness * WEIGHTS["pool_completeness"]
        + measurement * WEIGHTS["measurement_quality"]
        + specificity * WEIGHTS["factor_specificity"]
        + tier_component * WEIGHTS["methodology_tier"]
        + temporal * WEIGHTS["temporal_resolution"]
        + validation * WEIGHTS["validation_status"]
    )
    score = int(round(raw))

    if proxies and score > PROXY_CAP:
        penalties.append(f"Score limitado a {PROXY_CAP} por uso de proxy (era {score}).")
        score = PROXY_CAP

    if unvalidated and score > UNVALIDATED_FACTOR_CAP:
        penalties.append(
            f"Score limitado a {UNVALIDATED_FACTOR_CAP} por uso de fator não validado "
            f"(era {score})."
        )
        score = UNVALIDATED_FACTOR_CAP

    tier_label = f"Tier {max_tier}"
    if any(p.carbon_t.estimation_type == EstimationType.MEASURED for p in available):
        tier_label += " + measured inventory"

    return QualityResult(
        confidence_score=score,
        confidence_class=_classify(score),
        data_quality_score=compute_data_quality(stock, factor_service),
        methodology_tier=tier_label,
        drivers=drivers,
        penalties=penalties,
    )


def compute_data_quality(stock: CarbonStockResult, factor_service: FactorService) -> int:
    """Score de qualidade do DADO (independente do resultado de carbono).

    Avalia rastreabilidade, não magnitude:

        proveniência declarada .... 40
        fonte identificada ........ 25
        incerteza declarada ....... 20
        equação registrada ........ 15
    """
    available = _available_pools(stock)
    if not available:
        return 0

    with_provenance = sum(
        1 for p in available if p.carbon_t.estimation_type != EstimationType.NOT_AVAILABLE
    ) / len(available)
    with_source = sum(1 for p in available if p.carbon_t.source) / len(available)
    with_uncertainty = sum(1 for p in available if p.carbon_t.uncertainty_percent is not None) / len(
        available
    )
    with_equation = sum(
        1 for p in available if p.carbon_t.equations_used or p.carbon_t.factors_used
    ) / len(available)

    raw = with_provenance * 40 + with_source * 25 + with_uncertainty * 20 + with_equation * 15
    return int(round(raw))
