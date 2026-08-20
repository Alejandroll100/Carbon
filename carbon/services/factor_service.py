"""Resolução de fatores com rastro de decisão.

Hierarquia:

    measured → project_specific → species_specific → regional → national →
    biome_specific → climate_specific → ipcc_default → scientifically_valid_proxy

Toda resolução devolve um ``ResolutionTrace``: o que foi pedido, o que foi
escolhido, por quê, o que mais foi considerado, e se houve proxy.

Um PROXY é um fator aplicado FORA do seu domínio declarado de aplicabilidade.
Nunca é silencioso: exige autorização explícita (``allow_scientific_proxy``),
marca o resultado com ``proxy=True``, degrada o nível de dado para
``scientifically_valid_proxy`` e é recusado no modo científico estrito.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from ..factors.registry import (
    CarbonFactor,
    FactorNotFoundError,
    FactorRegistry,
    UnvalidatedFactorError,
)
from ..models.enums import DataLevel, ValidationStatus


class UnitMismatchError(ValueError):
    """Fator resolvido tem unidade incompatível com a esperada pelo cálculo."""


class ProxyNotAuthorizedError(RuntimeError):
    """Proxy necessário mas não autorizado."""


class AmbiguousFactorError(LookupError):
    """Vários fatores igualmente específicos, com valores diferentes.

    Empate na especificidade significa que o contexto informado não distingue
    entre eles. Escolher por ordem alfabética seria arbitrário e silencioso —
    o motor recusa e diz qual critério falta.
    """


class ResolutionTrace(BaseModel):
    requested: dict = Field(default_factory=dict)
    selected_factor: Optional[str] = None
    selection_reason: str = ""
    alternatives_considered: list[str] = Field(default_factory=list)
    rejected: list[dict] = Field(default_factory=list)
    data_level: Optional[DataLevel] = None
    proxy: bool = False
    proxy_description: Optional[str] = None
    resolved: bool = False


class FactorResolution(BaseModel):
    """Fator efetivamente aplicado a um cálculo."""

    factor_id: str
    category: str
    value: float
    unit: str
    gas: Optional[str] = None
    data_level: DataLevel
    tier: int
    reference_id: Optional[str] = None
    page_or_table: Optional[str] = None
    source_citation: Optional[str] = None
    methodology: Optional[str] = None
    validation_status: ValidationStatus
    uncertainty_percent: Optional[float] = None
    uncertainty_type: Optional[str] = None
    proxy: bool = False
    proxy_description: Optional[str] = None
    trace: ResolutionTrace = Field(default_factory=ResolutionTrace)
    warnings: list[str] = Field(default_factory=list)

    def to_audit(self) -> dict:
        return {
            "factor_id": self.factor_id,
            "category": self.category,
            "value": self.value,
            "unit": self.unit,
            "gas": self.gas,
            "data_level": self.data_level.value,
            "tier": self.tier,
            "reference_id": self.reference_id,
            "page_or_table": self.page_or_table,
            "validation_status": self.validation_status.value,
            "source_citation": self.source_citation,
            "proxy": self.proxy,
            "selection_reason": self.trace.selection_reason,
        }


class ProjectParameter(BaseModel):
    """Parâmetro fornecido pelo projeto (medição ou valor específico)."""

    value: float
    unit: str
    data_level: DataLevel = DataLevel.PROJECT_SPECIFIC
    source: str = "project_input"
    uncertainty_percent: Optional[float] = None


class ProxyAuthorization(BaseModel):
    """Autorização explícita para usar um fator fora do seu domínio."""

    factor_id: str
    justification: str


class FactorResolver:
    """Uma instância por cálculo — acumula rastro, warnings e lacunas."""

    def __init__(
        self,
        registry: FactorRegistry,
        *,
        project_parameters: Optional[dict[str, ProjectParameter]] = None,
        strict_factor_validation: bool = False,
        allow_scientific_proxy: bool = True,
    ) -> None:
        self.registry = registry
        self.project_parameters = project_parameters or {}
        self.strict = strict_factor_validation
        # Regra: no modo científico estrito, proxy é negado por padrão.
        self.allow_proxy = False if strict_factor_validation else allow_scientific_proxy
        self.used: list[FactorResolution] = []
        self.traces: list[ResolutionTrace] = []
        self.warnings: list[str] = []
        self.unresolved: list[dict] = []

    # -- API -------------------------------------------------------------------
    def resolve(
        self,
        category: str,
        *,
        purpose: str,
        expected_unit: Optional[str] = None,
        land_use: Optional[str] = None,
        agb_t_ha: Optional[float] = None,
        proxy: Optional[ProxyAuthorization] = None,
        **criteria,
    ) -> FactorResolution:
        requested = {"category": category, "purpose": purpose, "land_use": land_use, **criteria}
        trace = ResolutionTrace(requested=requested)

        # 1. parâmetro do projeto tem precedência absoluta
        param = self.project_parameters.get(category)
        if param is not None:
            trace.selected_factor = f"PROJECT::{category}"
            trace.selection_reason = (
                "Parâmetro específico do projeto tem precedência sobre a base de fatores."
            )
            trace.data_level = param.data_level
            trace.resolved = True
            resolution = FactorResolution(
                factor_id=f"PROJECT::{category}",
                category=category,
                value=param.value,
                unit=param.unit,
                data_level=param.data_level,
                tier=2,
                source_citation=param.source,
                methodology="project_specific_parameter",
                validation_status=ValidationStatus.PROJECT_SUPPLIED,
                uncertainty_percent=param.uncertainty_percent,
                trace=trace,
            )
            self._check_unit(resolution, expected_unit)
            return self._record(resolution)

        candidates = self.registry.find(
            category=category, land_use=land_use, agb_t_ha=agb_t_ha, **criteria
        )
        trace.alternatives_considered = [c.factor_id for c in candidates]

        usable: list[CarbonFactor] = []
        for c in candidates:
            reason = self._rejection_reason(c)
            if reason:
                trace.rejected.append({"factor_id": c.factor_id, "reason": reason})
            else:
                usable.append(c)

        if usable:
            self._assert_unambiguous(usable, category, purpose, trace)
            chosen = usable[0]
            trace.selected_factor = chosen.factor_id
            trace.data_level = chosen.data_level
            trace.resolved = True
            trace.selection_reason = (
                f"Fator mais específico disponível no nível de dado "
                f"'{chosen.data_level.value}' para o contexto solicitado."
            )
            resolution = self._build(chosen, trace)
            self._check_unit(resolution, expected_unit)
            return self._record(resolution)

        # 2. nenhum candidato utilizável → proxy explícito, se autorizado
        if proxy is not None:
            return self._resolve_proxy(proxy, category, purpose, trace, expected_unit)

        absences = [c for c in candidates if c.is_validated_absence]
        self.unresolved.append(
            {
                "category": category,
                "purpose": purpose,
                "requested": requested,
                "alternatives_considered": trace.alternatives_considered,
                "validated_absence": [c.factor_id for c in absences],
            }
        )
        self.traces.append(trace)
        raise FactorNotFoundError(self._not_found_message(category, purpose, candidates, absences))

    def try_resolve(self, category: str, **kwargs) -> Optional[FactorResolution]:
        try:
            return self.resolve(category, **kwargs)
        except (FactorNotFoundError, ProxyNotAuthorizedError, AmbiguousFactorError):
            return None

    def register_direct(self, resolution: FactorResolution) -> FactorResolution:
        return self._record(resolution)

    # -- interno ---------------------------------------------------------------
    def _rejection_reason(self, factor: CarbonFactor) -> Optional[str]:
        if factor.is_superseded:
            return (
                f"superado por edição mais recente da fonte ({factor.superseded_by}); "
                f"mantido apenas para auditoria"
            )
        if factor.is_validated_absence:
            return "ausência validada na fonte primária: não existe default para este caso"
        if not factor.has_value:
            return "fator cadastrado sem valor conferido"
        if factor.requires_validation and self.strict:
            return "REQUIRES_VALIDATION recusado sob strict_factor_validation"
        if self.strict and not factor.reference_id:
            return "sem reference_id: fonte ausente, recusado sob modo estrito"
        return None

    def _build(self, factor: CarbonFactor, trace: ResolutionTrace) -> FactorResolution:
        warnings: list[str] = []
        if factor.requires_validation:
            warnings.append(
                f"Fator {factor.factor_id} está REQUIRES_VALIDATION: valor não conferido "
                f"contra a fonte primária."
            )
        citation = None
        if factor.reference_id and factor.reference_id in self.registry.references:
            citation = self.registry.references.get(factor.reference_id).citation()
        return FactorResolution(
            factor_id=factor.factor_id,
            category=factor.category,
            value=float(factor.value),  # type: ignore[arg-type]
            unit=factor.unit,
            gas=factor.gas,
            data_level=factor.data_level,
            tier=factor.tier,
            reference_id=factor.reference_id,
            page_or_table=factor.page_or_table,
            source_citation=citation,
            methodology=factor.methodology,
            validation_status=factor.validation_status,
            uncertainty_percent=factor.uncertainty_as_percent(),
            uncertainty_type=factor.uncertainty_type,
            trace=trace,
            warnings=warnings,
        )

    def _resolve_proxy(
        self,
        proxy: ProxyAuthorization,
        category: str,
        purpose: str,
        trace: ResolutionTrace,
        expected_unit: Optional[str],
    ) -> FactorResolution:
        if not self.allow_proxy:
            trace.selection_reason = "Proxy necessário mas não autorizado."
            self.traces.append(trace)
            raise ProxyNotAuthorizedError(
                f"'{category}' ({purpose}) só seria resolvível por proxy "
                f"({proxy.factor_id}), e proxy não está autorizado "
                f"(allow_scientific_proxy=False ou modo científico estrito)."
            )
        factor = self.registry.get(proxy.factor_id)
        if not factor.has_value:
            raise FactorNotFoundError(f"Proxy {proxy.factor_id} não possui valor utilizável.")
        trace.selected_factor = factor.factor_id
        trace.data_level = DataLevel.SCIENTIFIC_PROXY
        trace.proxy = True
        trace.proxy_description = proxy.justification
        trace.resolved = True
        trace.selection_reason = (
            "PROXY: nenhum fator do domínio correto está disponível; fator de classe análoga "
            "aplicado sob autorização explícita."
        )
        resolution = self._build(factor, trace)
        resolution.data_level = DataLevel.SCIENTIFIC_PROXY
        resolution.proxy = True
        resolution.proxy_description = proxy.justification
        resolution.warnings.append(
            f"PROXY em uso para '{category}' ({purpose}): {factor.factor_id} aplicado fora do "
            f"seu domínio declarado. Justificativa: {proxy.justification}. Isto NÃO é medição "
            f"nem default do domínio correto."
        )
        self._check_unit(resolution, expected_unit)
        return self._record(resolution)

    def _assert_unambiguous(
        self,
        usable: list[CarbonFactor],
        category: str,
        purpose: str,
        trace: ResolutionTrace,
    ) -> None:
        """Recusa quando o topo do ranking empata com valores divergentes."""
        best_rank = self.registry.rank(usable[0])
        tied = [f for f in usable if self.registry.rank(f) == best_rank]
        distinct_values = {f.value for f in tied}
        if len(distinct_values) <= 1:
            return
        trace.selection_reason = "Empate de especificidade com valores divergentes."
        self.traces.append(trace)
        detail = "; ".join(f"{f.factor_id}={f.value} {f.unit}" for f in tied)
        raise AmbiguousFactorError(
            f"'{category}' ({purpose}): {len(tied)} fatores igualmente específicos com valores "
            f"diferentes [{detail}]. O contexto informado não distingue entre eles — informe o "
            f"critério que falta em vez de aceitar uma escolha arbitrária."
        )

    def _check_unit(self, resolution: FactorResolution, expected_unit: Optional[str]) -> None:
        if expected_unit and resolution.unit != expected_unit:
            raise UnitMismatchError(
                f"Fator {resolution.factor_id} tem unidade '{resolution.unit}', "
                f"o cálculo espera '{expected_unit}'."
            )

    def _not_found_message(
        self,
        category: str,
        purpose: str,
        candidates: list[CarbonFactor],
        absences: list[CarbonFactor],
    ) -> str:
        if absences:
            notes = " ".join(a.notes or "" for a in absences)
            return (
                f"'{category}' ({purpose}): AUSÊNCIA VALIDADA na fonte primária. {notes} "
                f"Forneça medição, parâmetro do projeto, fator regional revisado por pares, "
                f"ou autorize um proxy explícito."
            )
        if candidates:
            ids = ", ".join(c.factor_id for c in candidates)
            return (
                f"'{category}' ({purpose}): existem fatores cadastrados [{ids}] mas nenhum "
                f"utilizável no contexto/modo atual. O motor não preenche esta lacuna."
            )
        return f"'{category}' ({purpose}): nenhum fator cadastrado atende ao contexto solicitado."

    def _record(self, resolution: FactorResolution) -> FactorResolution:
        if resolution.validation_status == ValidationStatus.REQUIRES_VALIDATION and self.strict:
            raise UnvalidatedFactorError(
                f"{resolution.factor_id} é REQUIRES_VALIDATION e strict_factor_validation=True."
            )
        self.used.append(resolution)
        self.traces.append(resolution.trace)
        for w in resolution.warnings:
            if w not in self.warnings:
                self.warnings.append(w)
        return resolution

    def audit_trail(self) -> list[dict]:
        seen: set[str] = set()
        trail: list[dict] = []
        for r in self.used:
            if r.factor_id in seen:
                continue
            seen.add(r.factor_id)
            trail.append(r.to_audit())
        return trail

    def resolution_traces(self) -> list[dict]:
        return [t.model_dump(mode="json") for t in self.traces]

    @property
    def used_proxy(self) -> bool:
        return any(r.proxy for r in self.used)


#: Alias de compatibilidade com a versão 0.1.0.
FactorService = FactorResolver
