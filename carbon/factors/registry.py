"""Modelo de fator, bibliografia machine-readable e registro central.

Nunca armazenar ``factor = 0.47``. Todo fator é um objeto com fonte
identificada por ``reference_id``, tabela/página, tier, nível de dado,
incerteza e status de validação científica.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Optional

from pydantic import BaseModel, Field, model_validator

from ..models.enums import DATA_LEVEL_PRIORITY, DataLevel, ValidationStatus

DEFAULTS_PATH = Path(__file__).with_name("defaults.json")
REFERENCES_PATH = Path(__file__).with_name("references.json")


class FactorNotFoundError(LookupError):
    """Nenhum fator atende aos critérios de seleção."""


class UnvalidatedFactorError(RuntimeError):
    """Fator não validado usado sob modo científico estrito."""


class ReferenceNotFoundError(LookupError):
    """``reference_id`` não existe na bibliografia."""


class Reference(BaseModel):
    reference_id: str
    title: str
    organization: Optional[str] = None
    year: Optional[int] = None
    document: Optional[str] = None
    chapter: Optional[str] = None
    url: Optional[str] = None
    doi: Optional[str] = None
    access_level: str = "not_accessed"
    accessed_at: Optional[str] = None
    notes: Optional[str] = None

    def citation(self) -> str:
        parts = [p for p in (self.organization, str(self.year) if self.year else None, self.title) if p]
        return ". ".join(parts)


class CarbonFactor(BaseModel):
    """Um fator científico com proveniência completa."""

    factor_id: str
    category: str
    #: ``None`` = fator REGISTRADO mas SEM VALOR utilizável. Nunca é tratado como 0.
    value: Optional[float] = None
    unit: str
    gas: Optional[str] = None
    pool: Optional[str] = None

    # --- domínio de aplicabilidade ---
    country: Optional[str] = None
    region: Optional[str] = None
    climate_region: Optional[str] = None
    temperature_regime: Optional[str] = None
    moisture_regime: Optional[str] = None
    ecological_zone: Optional[str] = None
    soil_type: Optional[str] = None
    land_use: list[str] = Field(default_factory=list)
    forest_type: Optional[str] = None
    vegetation_type: Optional[str] = None
    species: Optional[str] = None
    #: [min, max]; ``None`` no topo = sem limite superior declarado na fonte.
    agb_range_t_ha: Optional[list[Optional[float]]] = None
    continent: Optional[str] = None
    #: Natural vs plantada (coluna "Origin" da Tabela 4.4 de 2019).
    origin: Optional[str] = None
    #: Primária / secundária >20 anos / secundária <=20 anos (Tabela 4.7 de 2019).
    status_condition: Optional[str] = None
    year: Optional[int] = None
    factor_kind: Optional[str] = None
    level: Optional[str] = None

    # --- proveniência ---
    reference_id: Optional[str] = None
    page_or_table: Optional[str] = None
    doi_or_official_identifier: Optional[str] = None
    methodology: Optional[str] = None
    tier: int = 1
    data_level: DataLevel = DataLevel.IPCC_DEFAULT
    uncertainty_percent: Optional[float] = None
    #: Desvio-padrão ABSOLUTO, na mesma unidade do valor. A Tabela 4.4 de 2019
    #: reporta ora ±90% (default IPCC), ora SD absoluto — confundir os dois
    #: distorce a propagação de incerteza em uma ordem de grandeza.
    uncertainty_absolute: Optional[float] = None
    #: "default_90pct" | "standard_deviation" | "range" | "confidence_interval_95"
    uncertainty_type: Optional[str] = None
    value_range: Optional[list[float]] = None
    validation_status: ValidationStatus = ValidationStatus.REQUIRES_VALIDATION
    #: ``reference_id`` da edição que substituiu este fator. Um fator superado
    #: permanece na base para auditoria e reprodução de exemplos históricos,
    #: mas NUNCA é selecionado em produção.
    superseded_by: Optional[str] = None
    validated_by: Optional[str] = None
    validated_at: Optional[str] = None
    version: Optional[str] = None
    notes: Optional[str] = None

    @model_validator(mode="after")
    def _check_provenance(self) -> "CarbonFactor":
        if self.validation_status == ValidationStatus.VALIDATED:
            if not self.reference_id:
                raise ValueError(f"{self.factor_id}: fator 'validated' exige reference_id")
            if not self.validated_by or not self.validated_at:
                raise ValueError(f"{self.factor_id}: fator 'validated' exige validated_by e validated_at")
            if self.value is None:
                raise ValueError(f"{self.factor_id}: fator 'validated' não pode ter value nulo")
        if not self.unit:
            raise ValueError(f"{self.factor_id}: unidade obrigatória")
        return self

    @property
    def has_value(self) -> bool:
        return self.value is not None

    @property
    def requires_validation(self) -> bool:
        return self.validation_status == ValidationStatus.REQUIRES_VALIDATION

    @property
    def is_superseded(self) -> bool:
        return self.superseded_by is not None

    @property
    def is_validated_absence(self) -> bool:
        """Ausência confirmada na fonte primária — não é falta de pesquisa."""
        return self.validation_status == ValidationStatus.NO_DEFAULT_AVAILABLE

    def applies_to_agb(self, agb_t_ha: Optional[float]) -> bool:
        if not self.agb_range_t_ha:
            return True
        if agb_t_ha is None:
            return False
        low, high = self.agb_range_t_ha
        if low is not None and agb_t_ha < low:
            return False
        if high is not None and agb_t_ha > high:
            return False
        return True

    def uncertainty_as_percent(self) -> Optional[float]:
        """Incerteza relativa, convertendo SD absoluto quando necessário.

        A conversão SD -> % só é lícita porque a propagação por produto usada
        no motor trabalha com coeficientes de variação. O tipo original fica
        registrado em ``uncertainty_type``.
        """
        if self.uncertainty_percent is not None:
            return self.uncertainty_percent
        if self.uncertainty_absolute is not None and self.value:
            return abs(self.uncertainty_absolute / self.value) * 100.0
        return None


class ReferenceLibrary:
    def __init__(self, references: Iterable[Reference] = (), *, version: str = "unknown"):
        self._refs = {r.reference_id: r for r in references}
        self.version = version

    @classmethod
    def load_default(cls, path: Path | None = None) -> "ReferenceLibrary":
        payload = json.loads((path or REFERENCES_PATH).read_text(encoding="utf-8"))
        return cls(
            (Reference(**r) for r in payload["references"]),
            version=payload.get("reference_database_version", "unknown"),
        )

    def get(self, reference_id: str) -> Reference:
        try:
            return self._refs[reference_id]
        except KeyError as exc:
            raise ReferenceNotFoundError(f"reference_id desconhecido: {reference_id}") from exc

    def all(self) -> list[Reference]:
        return list(self._refs.values())

    def __contains__(self, reference_id: object) -> bool:
        return reference_id in self._refs


class FactorRegistry:
    """Registro em memória. Substituível por repositório de banco."""

    def __init__(
        self,
        factors: Iterable[CarbonFactor] | None = None,
        *,
        version: str = "unknown",
        references: Optional[ReferenceLibrary] = None,
    ):
        self._factors: dict[str, CarbonFactor] = {}
        self._last_rank_context: tuple[Optional[str], dict] = (None, {})
        self.version = version
        self.references = references or ReferenceLibrary()
        for f in factors or []:
            self.add(f)

    @classmethod
    def load_default(cls, path: Path | None = None) -> "FactorRegistry":
        payload = json.loads((path or DEFAULTS_PATH).read_text(encoding="utf-8"))
        references = ReferenceLibrary.load_default()
        registry = cls(version=payload.get("factor_database_version", "unknown"), references=references)
        for raw in payload["factors"]:
            registry.add(CarbonFactor(**raw))
        registry.verify_references()
        return registry

    def add(self, factor: CarbonFactor) -> None:
        if factor.factor_id in self._factors:
            raise ValueError(f"factor_id duplicado: {factor.factor_id}")
        self._factors[factor.factor_id] = factor

    def verify_references(self) -> None:
        """Nenhum fator pode apontar para bibliografia inexistente."""
        missing = sorted(
            {
                f.reference_id
                for f in self._factors.values()
                if f.reference_id and f.reference_id not in self.references
            }
        )
        if missing:
            raise ReferenceNotFoundError(f"reference_id inexistentes em references.json: {missing}")

    def get(self, factor_id: str) -> CarbonFactor:
        try:
            return self._factors[factor_id]
        except KeyError as exc:
            raise FactorNotFoundError(f"factor_id desconhecido: {factor_id}") from exc

    def all(self) -> list[CarbonFactor]:
        return list(self._factors.values())

    # -- consulta --------------------------------------------------------------
    MATCH_FIELDS = (
        "country",
        "region",
        "climate_region",
        "temperature_regime",
        "moisture_regime",
        "ecological_zone",
        "soil_type",
        "forest_type",
        "vegetation_type",
        "species",
        "gas",
        "pool",
        "factor_kind",
        "level",
        "year",
        "continent",
        "origin",
        "status_condition",
    )

    def find(
        self,
        *,
        category: str,
        land_use: Optional[str] = None,
        agb_t_ha: Optional[float] = None,
        **criteria,
    ) -> list[CarbonFactor]:
        """Candidatos ordenados por hierarquia de dados e depois especificidade.

        Um campo ``None`` no fator significa "genérico" e continua candidato,
        com menor especificidade. Um campo preenchido que conflita elimina.
        """
        unknown = set(criteria) - set(self.MATCH_FIELDS)
        if unknown:
            raise ValueError(f"Critérios desconhecidos: {sorted(unknown)}")

        candidates: list[CarbonFactor] = []
        for f in self._factors.values():
            if f.category != category:
                continue
            if land_use and f.land_use and land_use not in f.land_use:
                continue
            if not f.applies_to_agb(agb_t_ha):
                continue
            if any(
                wanted is not None and getattr(f, field) is not None and getattr(f, field) != wanted
                for field, wanted in criteria.items()
            ):
                continue
            candidates.append(f)

        def sort_key(f: CarbonFactor) -> tuple[int, int, str]:
            return (*self.rank(f, land_use=land_use, criteria=criteria), f.factor_id)

        ranked = sorted(candidates, key=sort_key)
        self._last_rank_context = (land_use, dict(criteria))
        return ranked

    def rank(
        self,
        factor: CarbonFactor,
        *,
        land_use: Optional[str] = None,
        criteria: Optional[dict] = None,
    ) -> tuple[int, int]:
        """(prioridade do nível de dado, -especificidade). Menor vence.

        A especificidade conta quantos critérios do pedido o fator responde
        explicitamente. Dois fatores com o mesmo rank são indistinguíveis
        para o contexto dado.
        """
        if criteria is None:
            land_use, criteria = getattr(self, "_last_rank_context", (None, {}))
        explicit = sum(
            1
            for field, wanted in criteria.items()
            if wanted is not None and getattr(factor, field) is not None
        )
        if land_use and factor.land_use:
            explicit += 1
        if factor.agb_range_t_ha:
            explicit += 1
        return (DATA_LEVEL_PRIORITY[factor.data_level.value], -explicit)
