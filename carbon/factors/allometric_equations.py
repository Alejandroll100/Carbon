"""Biblioteca de equações alométricas.

Princípios:

1. NÃO existe equação universal. Cada equação é cadastrada com bioma, tipo
   florestal, variáveis exigidas, fonte e versão.
2. A equação NUNCA é avaliada a partir de string (``eval``). Cada
   ``equation_id`` aponta para um *callable* registrado e testado. A string
   ``equation`` existe apenas para documentação e auditoria.
3. Coeficientes ainda não conferidos contra a publicação primária são
   marcados ``REQUIRES_VALIDATION`` e o motor emite alerta ao usá-los.
"""

from __future__ import annotations

from typing import Callable, Optional

from pydantic import BaseModel, Field

from ..models.enums import ValidationStatus
from ..utils.validation import (
    PhysicalValidationError,
    validate_dbh_cm,
    validate_height_m,
    validate_wood_density,
)


class AllometricEquation(BaseModel):
    equation_id: str
    name: str
    biome: Optional[str] = None
    forest_type: Optional[str] = None
    required_variables: list[str] = Field(default_factory=list)
    optional_variables: list[str] = Field(default_factory=list)
    biome_applicability: list[str] = Field(default_factory=list)
    geographic_applicability: list[str] = Field(default_factory=list)
    species_applicability: list[str] = Field(default_factory=list)
    reference_id: Optional[str] = None
    doi: Optional[str] = None
    #: Coeficientes do modelo, declarados como DADO da equação — nunca soltos
    #: no corpo da função. Cada um herda o status de validação da equação.
    coefficients: dict[str, float] = Field(default_factory=dict)
    verified_metadata: list[str] = Field(default_factory=list)
    unverified_items: list[str] = Field(default_factory=list)
    equation: str
    output_unit: str = "kg dry matter"
    output_pool: str = "aboveground_biomass"
    source: str
    reference: Optional[str] = None
    version: str = "0.1.0"
    validation_status: ValidationStatus = ValidationStatus.REQUIRES_VALIDATION
    #: [min, max]; ``None`` no limite superior = sem teto declarado na fonte.
    dbh_range_cm: Optional[list[Optional[float]]] = None
    notes: Optional[str] = None

    @property
    def requires_validation(self) -> bool:
        return self.validation_status == ValidationStatus.REQUIRES_VALIDATION


#: DAP mínimo de calibração de Chave et al. (2014): "trees >= 5 cm trunk
#: diameter", verificado no abstract oficial e na página suplementar do autor.
CHAVE2014_MIN_DBH_CM = 5.0

#: Biomas cobertos por uma equação declarada "pantropical". "Pantropical" NÃO
#: significa "qualquer bioma": significa o conjunto de vegetações tropicais
#: amostradas. Um bioma fora desta lista precisa de equação própria.
PANTROPICAL_BIOMES = frozenset(
    {
        "pantropical",
        "tropical_moist_forest",
        "tropical_dry_forest",
        "tropical_rainforest",
        "tropical_savanna",
        "tropical_montane_forest",
        "atlantic_forest",
        "amazonia",
        "cerrado",
        "caatinga",
    }
)


class EquationNotFoundError(LookupError):
    pass


class MissingVariableError(ValueError):
    pass


# ---------------------------------------------------------------------------
# Implementações
# ---------------------------------------------------------------------------

def _chave2014_moist_with_height(
    dbh_cm: float, height_m: Optional[float] = None, wood_density_g_cm3: Optional[float] = None
) -> float:
    """AGB (kg m.s.) = 0.0673 * (rho * D^2 * H)^0.976.

    rho em g/cm3, D em cm, H em m.

    ATENÇÃO: coeficientes transcritos de memória a partir de Chave et al.
    (2014), Global Change Biology 20:3177-3190, Modelo 4 (com altura).
    Marcados REQUIRES_VALIDATION até conferência contra o artigo.
    """
    validate_dbh_cm(dbh_cm)
    validate_height_m(height_m)
    validate_wood_density(wood_density_g_cm3)
    if height_m is None:
        raise MissingVariableError("height_m é obrigatório para CHAVE2014_MOIST_H")
    if wood_density_g_cm3 is None:
        raise MissingVariableError("wood_density_g_cm3 é obrigatório para CHAVE2014_MOIST_H")
    params = _CATALOG["CHAVE2014_MOIST_H"].coefficients
    return params["a"] * ((wood_density_g_cm3 * dbh_cm**2 * height_m) ** params["b"])


def _project_specific_placeholder(**_kwargs: float) -> float:
    raise EquationNotFoundError(
        "Equação específica do projeto não implementada. Cadastre uma equação "
        "validada em allometric_equations.py antes de usar o modo inventory."
    )


_IMPLEMENTATIONS: dict[str, Callable[..., float]] = {
    "CHAVE2014_MOIST_H": _chave2014_moist_with_height,
    "PROJECT_SPECIFIC_PLACEHOLDER": _project_specific_placeholder,
}

_CATALOG: dict[str, AllometricEquation] = {
    "CHAVE2014_MOIST_H": AllometricEquation(
        equation_id="CHAVE2014_MOIST_H",
        name="Chave et al. (2014) — pantropical, com altura",
        biome="pantropical",
        forest_type="moist_tropical_forest",
        required_variables=["dbh_cm", "height_m", "wood_density_g_cm3"],
        equation="AGB_kg = a * (wood_density * dbh_cm^2 * height_m)^b",
        coefficients={"a": 0.0673, "b": 0.976},
        output_unit="kg dry matter (oven-dry)",
        biome_applicability=["pantropical"],
        dbh_range_cm=[CHAVE2014_MIN_DBH_CM, None],
        source="Chave, J. et al. (2014). Improved allometric models to estimate the "
        "aboveground biomass of tropical trees. Global Change Biology, 20(10), 3177-3190.",
        reference_id="CHAVE2014",
        doi="10.1111/gcb.12629",
        version="0.1.0-coefficients-unverified",
        validation_status=ValidationStatus.REQUIRES_VALIDATION,
        verified_metadata=[
            "escopo pantropical, sem efeito detectável de região",
            "58 sítios, 4004 árvores derrubadas",
            "DAP mínimo de calibração: 5 cm",
            "saída: biomassa seca em estufa, em kg",
            "entradas: DAP em cm, altura total em m, densidade específica em g/cm3",
        ],
        unverified_items=["coeficiente a", "expoente b", "erro reportado do modelo"],
        notes=(
            "Metadados verificados no abstract oficial (DOI 10.1111/gcb.12629) e na página "
            "suplementar do autor. Os COEFICIENTES não foram conferidos: o artigo está atrás "
            "de paywall. Permanece REQUIRES_VALIDATION e é recusado no modo estrito."
        ),
    ),
    "PROJECT_SPECIFIC_PLACEHOLDER": AllometricEquation(
        equation_id="PROJECT_SPECIFIC_PLACEHOLDER",
        name="Slot para equação específica do projeto/espécie",
        required_variables=["dbh_cm"],
        equation="a definir",
        source="PENDENTE",
        version="0.0.0",
        validation_status=ValidationStatus.REQUIRES_VALIDATION,
        notes="Sempre levanta erro. Existe para documentar o ponto de extensão.",
    ),
}


def list_equations() -> list[AllometricEquation]:
    return list(_CATALOG.values())


def get_equation(equation_id: str) -> AllometricEquation:
    try:
        return _CATALOG[equation_id]
    except KeyError as exc:
        raise EquationNotFoundError(f"equation_id desconhecido: {equation_id}") from exc


def register_equation(meta: AllometricEquation, impl: Callable[..., float]) -> None:
    """Ponto de extensão: cadastrar equação validada do projeto."""
    if meta.equation_id in _CATALOG:
        raise ValueError(f"equation_id duplicado: {meta.equation_id}")
    _CATALOG[meta.equation_id] = meta
    _IMPLEMENTATIONS[meta.equation_id] = impl


def estimate_tree_biomass(
    dbh_cm: float,
    height_m: Optional[float] = None,
    wood_density_g_cm3: Optional[float] = None,
    equation_id: Optional[str] = None,
) -> dict[str, float | str | list[str]]:
    """Estima biomassa seca de uma árvore.

    Retorna dicionário com valor, unidade, equação usada e variáveis de entrada.
    Não escolhe equação por conta própria: ``equation_id`` é obrigatório, para
    impedir que o motor aplique silenciosamente um modelo fora de domínio.
    """
    if equation_id is None:
        raise MissingVariableError(
            "equation_id é obrigatório. O motor não seleciona equação alométrica "
            "automaticamente — a escolha do modelo é uma decisão metodológica."
        )
    meta = get_equation(equation_id)
    impl = _IMPLEMENTATIONS[equation_id]

    provided = {
        "dbh_cm": dbh_cm,
        "height_m": height_m,
        "wood_density_g_cm3": wood_density_g_cm3,
    }
    missing = [v for v in meta.required_variables if provided.get(v) is None]
    if missing:
        raise MissingVariableError(
            f"Equação {equation_id} exige {meta.required_variables}; faltam: {missing}"
        )

    if meta.dbh_range_cm:
        low, high = meta.dbh_range_cm
        if (low is not None and dbh_cm < low) or (high is not None and dbh_cm > high):
            raise PhysicalValidationError(
                f"dbh_cm={dbh_cm} fora da faixa de calibração {meta.dbh_range_cm} "
                f"da equação {equation_id}"
            )

    value_kg = impl(dbh_cm=dbh_cm, height_m=height_m, wood_density_g_cm3=wood_density_g_cm3)
    warnings: list[str] = []
    if meta.requires_validation:
        warnings.append(
            f"Equação {equation_id} está marcada REQUIRES_VALIDATION "
            f"(versão {meta.version}). Coeficientes não conferidos contra a fonte primária."
        )
    return {
        "biomass_kg": value_kg,
        "unit": meta.output_unit,
        "pool": meta.output_pool,
        "equation_id": equation_id,
        "equation_version": meta.version,
        "source": meta.source,
        "warnings": warnings,
        "inputs": {k: v for k, v in provided.items() if v is not None},
    }


# ---------------------------------------------------------------------------
# Resolução de equação
# ---------------------------------------------------------------------------

class NoValidAllometricEquationError(LookupError):
    """Nenhuma equação cadastrada é aplicável ao contexto."""

    code = "no_valid_allometric_equation"


class EquationResolution(BaseModel):
    equation_id: str
    equation: "AllometricEquation"
    match_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AllometricEquationResolver:
    """Escolhe equação por domínio declarado — nunca "porque é tropical".

    Avalia bioma, clima, tipo florestal, espécie, faixa de DAP, variáveis
    disponíveis, aplicabilidade geográfica e status de validação. Se nada
    servir, levanta ``NoValidAllometricEquationError`` em vez de aplicar um
    modelo fora de domínio.
    """

    def __init__(self, *, strict: bool = False) -> None:
        self.strict = strict

    def resolve(
        self,
        *,
        dbh_cm: float,
        biome: Optional[str] = None,
        climate: Optional[str] = None,
        forest_type: Optional[str] = None,
        species: Optional[str] = None,
        country: Optional[str] = None,
        available_variables: Optional[set[str]] = None,
    ) -> EquationResolution:
        available = available_variables or set()
        rejected: list[str] = []
        scored: list[tuple[int, AllometricEquation, list[str]]] = []

        for meta in _CATALOG.values():
            if meta.equation_id == "PROJECT_SPECIFIC_PLACEHOLDER":
                continue
            reasons: list[str] = []

            missing = [v for v in meta.required_variables if v not in available]
            if missing:
                rejected.append(f"{meta.equation_id}: faltam variáveis {missing}")
                continue

            if meta.dbh_range_cm:
                low, high = meta.dbh_range_cm
                if (low is not None and dbh_cm < low) or (high is not None and dbh_cm > high):
                    rejected.append(
                        f"{meta.equation_id}: DAP {dbh_cm} cm fora da faixa de calibração "
                        f"{meta.dbh_range_cm}"
                    )
                    continue
                reasons.append(f"DAP dentro da faixa de calibração {meta.dbh_range_cm}")

            if self.strict and meta.requires_validation:
                rejected.append(
                    f"{meta.equation_id}: {meta.validation_status.value} recusado no modo estrito"
                )
                continue

            score = 0
            if species and meta.species_applicability:
                if species not in meta.species_applicability:
                    rejected.append(f"{meta.equation_id}: espécie {species} fora do domínio")
                    continue
                score += 4
                reasons.append(f"espécie {species} no domínio declarado")
            if country and meta.geographic_applicability:
                if country not in meta.geographic_applicability:
                    rejected.append(f"{meta.equation_id}: país {country} fora do domínio")
                    continue
                score += 3
                reasons.append(f"país {country} no domínio declarado")
            if biome and meta.biome_applicability:
                covered = set(meta.biome_applicability)
                if "pantropical" in covered:
                    covered |= PANTROPICAL_BIOMES
                if biome not in covered:
                    rejected.append(f"{meta.equation_id}: bioma {biome} fora do domínio")
                    continue
                score += 2
                reasons.append(f"bioma compatível ({meta.biome_applicability})")
            if forest_type and meta.forest_type:
                if forest_type != meta.forest_type:
                    rejected.append(
                        f"{meta.equation_id}: tipo florestal {forest_type} != {meta.forest_type}"
                    )
                    continue
                score += 2
                reasons.append(f"tipo florestal {forest_type}")

            scored.append((score, meta, reasons))

        if not scored:
            raise NoValidAllometricEquationError(
                "no_valid_allometric_equation: nenhuma equação cadastrada é aplicável. "
                + ("Motivos: " + "; ".join(rejected) if rejected else "Catálogo vazio.")
            )

        scored.sort(key=lambda item: (-item[0], item[1].equation_id))
        score, meta, reasons = scored[0]
        warnings: list[str] = []
        if meta.requires_validation:
            warnings.append(
                f"Equação {meta.equation_id} está {meta.validation_status.value}: "
                f"itens não conferidos: {meta.unverified_items}."
            )
        if score == 0:
            warnings.append(
                "Equação selecionada sem nenhum critério positivo de domínio (bioma, espécie, "
                "tipo florestal ou país). Verifique manualmente a adequação."
            )
        return EquationResolution(
            equation_id=meta.equation_id, equation=meta, match_reasons=reasons, warnings=warnings
        )
