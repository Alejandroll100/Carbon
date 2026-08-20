"""Modelos de resultado.

Separação obrigatória (§1):

    Carbon Inventory      -> implementado
    Carbon Stock Estimate -> implementado
    Carbon Removal Estimate -> implementado
    Carbon Credit Potential -> NÃO implementado nesta versão
    Verified Carbon Credits -> NÃO implementado nesta versão

O motor produz estimativa técnica. Nenhum resultado representa crédito de
carbono, certificação, auditoria ou adicionalidade.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

from .enums import CalculationMode, CarbonPool, ConfidenceClass, ResultStatus
from .provenance import TracedValue, UncertaintyRange

DISCLAIMER = (
    "Estimativa técnica de estoque, remoções e mudanças de estoque de carbono. "
    "NÃO constitui crédito de carbono, crédito comercializável, certificação "
    "(Verra, Gold Standard ou equivalente), resultado auditado nem garantia de "
    "adicionalidade. Créditos exigem metodologia aprovada, baseline, "
    "adicionalidade, permanência, leakage, MRV, auditoria independente e registro."
)


class PoolResult(BaseModel):
    """Resultado de um pool de carbono."""

    pool: CarbonPool
    dry_biomass_t: Optional[TracedValue] = None
    carbon_t: TracedValue
    co2e_t: Optional[float] = None
    carbon_t_ha: Optional[float] = None
    co2e_t_ha: Optional[float] = None
    uncertainty: UncertaintyRange = Field(default_factory=UncertaintyRange)

    @property
    def available(self) -> bool:
        return self.carbon_t.available


class CarbonStockResult(BaseModel):
    """Estoque em um instante. Pools indisponíveis permanecem ``None``."""

    inventory_id: Optional[str] = None
    year: Optional[int] = None
    area_ha: float
    pools: dict[str, PoolResult] = Field(default_factory=dict)
    total_carbon_t: Optional[float] = None
    total_co2e_t: Optional[float] = None
    carbon_t_ha: Optional[float] = None
    co2e_t_ha: Optional[float] = None
    available_pools: list[str] = Field(default_factory=list)
    missing_pools: list[str] = Field(default_factory=list)
    uncertainty: UncertaintyRange = Field(default_factory=UncertaintyRange)
    status: ResultStatus = ResultStatus.PARTIAL


class PoolChange(BaseModel):
    pool: str
    baseline_carbon_t: Optional[float] = None
    current_carbon_t: Optional[float] = None
    delta_carbon_t: Optional[float] = None
    comparable: bool = False
    reason: Optional[str] = None


class StockChangeResult(BaseModel):
    """ΔC entre dois inventários.

    Só entram no total pools presentes NOS DOIS períodos. Pool medido só em um
    período é reportado separadamente e nunca tratado como zero no outro.
    """

    baseline_year: int
    current_year: int
    period_years: int
    comparable_pools: list[str] = Field(default_factory=list)
    non_comparable_pools: list[PoolChange] = Field(default_factory=list)
    pool_changes: list[PoolChange] = Field(default_factory=list)
    baseline_comparable_carbon_t: Optional[float] = None
    current_comparable_carbon_t: Optional[float] = None
    delta_carbon_t: Optional[float] = None
    delta_co2e_t: Optional[float] = None
    direction: Optional[str] = None
    status: ResultStatus = ResultStatus.PARTIAL
    notes: list[str] = Field(default_factory=list)


class RemovalResult(BaseModel):
    """Remoção anualizada derivada da mudança de estoque.

    Valores negativos significam PERDA líquida de estoque, não remoção. O campo
    ``is_removal`` explicita isso.
    """

    period_years: int
    carbon_stock_change_tC: Optional[float] = None
    co2_stock_change_tCO2e: Optional[float] = None
    annual_carbon_change_tC: Optional[float] = None
    annual_co2_removal_tCO2e_year: Optional[float] = None
    annual_co2_removal_tCO2e_ha_year: Optional[float] = None
    is_removal: Optional[bool] = None
    method: str = "linear_annualization"
    notes: list[str] = Field(default_factory=list)


class LossResult(BaseModel):
    total_carbon_loss_tC: Optional[float] = None
    total_co2e_loss_tCO2e: Optional[float] = None
    quantified_events: int = 0
    unquantified_events: int = 0
    events: list[dict] = Field(default_factory=list)


class OperationalEmissionsResult(BaseModel):
    total_tCO2e: Optional[float] = None
    resolved_entries: int = 0
    unresolved_entries: int = 0
    entries: list[dict] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class NetBalanceResult(BaseModel):
    """Net = Remoções brutas - Perdas de carbono - Emissões operacionais.

    Nenhum componente é escondido dentro do número final.
    """

    gross_removals_tCO2e: Optional[float] = None
    carbon_losses_tCO2e: Optional[float] = None
    operational_emissions_tCO2e: Optional[float] = None
    net_balance_tCO2e: Optional[float] = None
    status: ResultStatus = ResultStatus.PARTIAL
    excluded_components: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class QualityResult(BaseModel):
    confidence_score: int
    confidence_class: ConfidenceClass
    data_quality_score: int
    methodology_tier: str
    drivers: list[str] = Field(default_factory=list)
    penalties: list[str] = Field(default_factory=list)
    disclaimer: str = (
        "confidence_score é um indicador interno GEØ.IA de qualidade e completude "
        "dos dados. Não é certificação científica, não é probabilidade e não "
        "substitui análise de incerteza estatística."
    )


class Insight(BaseModel):
    type: str
    message: str
    severity: str = "info"


class AuditRecord(BaseModel):
    """Registro reprodutível do cálculo."""

    calculation_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    engine_version: str
    factor_database_version: str
    methodology_version: str
    calculation_mode: CalculationMode
    input_fingerprint: str
    input_snapshot: dict = Field(default_factory=dict)
    factors_used: list[dict] = Field(default_factory=list)
    equations_used: list[dict] = Field(default_factory=list)
    resolution_traces: list[dict] = Field(default_factory=list)
    reference_database_version: Optional[str] = None
    gwp_version: Optional[str] = None
    strict_factor_validation: bool = False
    allow_scientific_proxy: bool = True
    warnings: list[str] = Field(default_factory=list)


class CarbonResult(BaseModel):
    """Saída principal do endpoint de cálculo."""

    project_id: str
    area_ha: float
    land_use: str
    calculation_mode: CalculationMode
    result_type: str = "carbon_stock_and_removal_estimate"
    status: ResultStatus = ResultStatus.PARTIAL
    carbon_stock: Optional[CarbonStockResult] = None
    baseline_stock: Optional[CarbonStockResult] = None
    change: Optional[StockChangeResult] = None
    removal: Optional[RemovalResult] = None
    losses: Optional[LossResult] = None
    operational_emissions: Optional[OperationalEmissionsResult] = None
    net_balance: Optional[NetBalanceResult] = None
    quality: Optional[QualityResult] = None
    insights: list[Insight] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    unresolved_factors: list[dict] = Field(default_factory=list)
    sanity_findings: list[dict] = Field(default_factory=list)
    proxy_used: bool = False
    validation_warnings: list[str] = Field(default_factory=list)
    methodology: dict = Field(default_factory=dict)
    audit: Optional[AuditRecord] = None
    disclaimer: str = DISCLAIMER
