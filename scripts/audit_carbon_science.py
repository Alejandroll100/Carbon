"""Auditoria científica automática da base de fatores e das equações.

Executar:  python -m scripts.audit_carbon_science [--strict]

Procura, sem exceção:

* fatores ``REQUIRES_VALIDATION``;
* fatores com valor ``null``;
* fatores sem fonte, sem unidade ou sem tabela/página;
* ``reference_id`` apontando para bibliografia inexistente;
* fatores marcados ``validated`` sem ``validated_by`` ou ``validated_at``;
* equações alométricas não validadas;
* números científicos hardcoded fora das constantes permitidas.

Saída: SCIENTIFIC READINESS REPORT. Código de saída 1 se houver achado
bloqueante para o conjunto auditado.
"""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from carbon.factors.allometric_equations import list_equations  # noqa: E402
from carbon.factors.registry import FactorRegistry  # noqa: E402
from carbon.models.enums import ValidationStatus  # noqa: E402

CARBON_DIR = ROOT / "carbon"

#: Constantes científicas que PODEM aparecer no código, com justificativa.
#: São razões de massa molar e identidades de unidade — exatas por definição.
ALLOWED_CONSTANTS: dict[float, str] = {
    44.0: "massa molar do CO2 / N2O (razão exata)",
    12.0: "massa molar do carbono (razão exata)",
    28.0: "massa molar do N2 (razão exata)",
    10_000.0: "m2 por hectare (identidade de unidade)",
    1_000.0: "kg por tonelada (identidade de unidade)",
    100.0: "conversão percentual / cm por metro",
    30.0: "profundidade de referência do IPCC para SOC (parâmetro metodológico documentado)",
    20.0: "período de transição/referência default do IPCC (parâmetro metodológico documentado)",
    1.96: "escore z para IC 95% (constante estatística)",
}
#: Arquivos onde limiares operacionais são declarados de propósito.
CONSTANT_ALLOWLIST_FILES = {
    "sanity.py",  # limiares operacionais de plausibilidade, declarados como tais
    "confidence_engine.py",  # pesos do score, não fatores científicos
    "units.py",  # identidades de unidade e razões de massa molar
    "gwp.py",  # registro de GWP, vazio por ora
    "validation.py",  # limites físicos nomeados com justificativa
}
SKIP_DIRS = {"tests", "__pycache__"}


@dataclass
class Report:
    blocking: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)

    def block(self, msg: str) -> None:
        self.blocking.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)


def audit_factors(registry: FactorRegistry, report: Report) -> dict:
    factors = registry.all()
    validated, pending, absence, without_value = [], [], [], []

    superseded = [f.factor_id for f in factors if f.is_superseded]
    for f in factors:
        if f.is_superseded and not f.superseded_by:
            report.block(f"{f.factor_id}: marcado superado sem indicar por qual fonte")
        if not f.unit:
            report.block(f"{f.factor_id}: sem unidade")
        if f.validation_status == ValidationStatus.VALIDATED:
            validated.append(f.factor_id)
            if not f.reference_id:
                report.block(f"{f.factor_id}: 'validated' sem reference_id")
            if not f.page_or_table:
                report.block(f"{f.factor_id}: 'validated' sem tabela/página")
            if not f.validated_by:
                report.block(f"{f.factor_id}: 'validated' sem validated_by")
            if not f.validated_at:
                report.block(f"{f.factor_id}: 'validated' sem validated_at")
            if f.value is None:
                report.block(f"{f.factor_id}: 'validated' com valor nulo")
        elif f.validation_status == ValidationStatus.NO_DEFAULT_AVAILABLE:
            absence.append(f.factor_id)
            if not f.reference_id or not f.notes:
                report.block(
                    f"{f.factor_id}: ausência validada precisa citar a fonte que a declara"
                )
        elif f.validation_status == ValidationStatus.REQUIRES_VALIDATION:
            pending.append(f.factor_id)
            if not f.notes:
                report.block(f"{f.factor_id}: pendência sem justificativa registrada")
            report.warn(f"{f.factor_id}: REQUIRES_VALIDATION")

        if f.value is None:
            without_value.append(f.factor_id)

        if f.reference_id and f.reference_id not in registry.references:
            report.block(f"{f.factor_id}: reference_id inexistente ({f.reference_id})")

    return {
        "total": len(factors),
        "validated": validated,
        "pending": pending,
        "validated_absence": absence,
        "without_value": without_value,
        "superseded": superseded,
    }


def audit_equations(report: Report) -> dict:
    equations = [e for e in list_equations() if e.equation_id != "PROJECT_SPECIFIC_PLACEHOLDER"]
    validated = [e.equation_id for e in equations if not e.requires_validation]
    pending = [e.equation_id for e in equations if e.requires_validation]
    for e in equations:
        if e.requires_validation:
            report.warn(
                f"{e.equation_id}: equação não validada — pendente: {e.unverified_items or ['?']}"
            )
            if not e.unverified_items:
                report.block(f"{e.equation_id}: pendência sem itens declarados")
    return {"total": len(equations), "validated": validated, "pending": pending}


def audit_references(registry: FactorRegistry, report: Report) -> dict:
    used = {f.reference_id for f in registry.all() if f.reference_id}
    resolved = [r for r in used if r in registry.references]
    for reference in registry.references.all():
        if reference.access_level == "not_accessed" and reference.reference_id in used:
            report.warn(
                f"{reference.reference_id}: citada por fatores mas documento não consultado "
                f"diretamente"
            )
    return {"used": sorted(used), "resolved": sorted(resolved)}


def audit_hardcoded_numbers(report: Report) -> list[str]:
    """Procura número científico solto DENTRO de código executável.

    Declaração no escopo do módulo (constante nomeada, catálogo de equações,
    tabela de fatores) é exatamente o comportamento desejado e não é achado.
    O que se procura é o número aparecendo no meio de um cálculo, onde ninguém
    consegue auditar de onde ele veio.
    """
    findings: list[str] = []
    for path in sorted(CARBON_DIR.rglob("*.py")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.name in CONSTANT_ALLOWLIST_FILES:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover
            continue

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for inner in ast.walk(node):
                if not isinstance(inner, ast.Constant) or not isinstance(inner.value, float):
                    continue
                value = float(inner.value)
                if value in ALLOWED_CONSTANTS or value in (0.0, 1.0, 0.5, 2.0):
                    continue
                rel = path.relative_to(ROOT)
                findings.append(
                    f"{rel}:{inner.lineno}: constante científica solta {value} "
                    f"dentro de {node.name}()"
                )
    for finding in findings:
        report.block(finding)
    return findings


def quick_estimate_coverage() -> tuple[int, int, list[str]]:
    """Cobertura do quick_estimate por combinação clima x solo x uso da terra."""
    from carbon.core.carbon_engine import CarbonEngine
    from carbon.models.enums import CalculationMode, IPCCClimateRegion, IPCCSoilType, LandUse
    from carbon.models.inventory import CarbonInventory
    from carbon.models.project import CarbonProject, Coordinates

    engine = CarbonEngine()
    climates = [
        IPCCClimateRegion.TROPICAL_DRY,
        IPCCClimateRegion.TROPICAL_MOIST,
        IPCCClimateRegion.TROPICAL_WET,
    ]
    soils = [IPCCSoilType.LAC, IPCCSoilType.HAC, IPCCSoilType.SANDY]
    land_uses = [LandUse.AGROFORESTRY, LandUse.CROPLAND, LandUse.NATURAL_FOREST]

    ok, total, failures = 0, 0, []
    for climate in climates:
        for soil in soils:
            for land_use in land_uses:
                total += 1
                project = CarbonProject(
                    project_id="cov",
                    name="cov",
                    country="Brazil",
                    land_use=land_use,
                    area_ha=100.0,
                    coordinates=Coordinates(lat=-15.0, lon=-47.0),
                    reference_year=2026,
                    climate_region=climate,
                    soil_type=soil,
                    region="South America",
                    ecological_zone="humid_tropical_lowland",
                )
                inventory = CarbonInventory(
                    inventory_id="cov",
                    project_id="cov",
                    year=2026,
                    mode=CalculationMode.QUICK_ESTIMATE,
                )
                result = engine.calculate(project, inventory)
                stock = result.carbon_stock
                if stock is not None and stock.total_carbon_t:
                    ok += 1
                else:
                    failures.append(f"{climate.value}/{soil.value}/{land_use.value}")
    return ok, total, failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--strict",
        action="store_true",
        help="trata pendências de validação como bloqueantes",
    )
    args = parser.parse_args()

    report = Report()
    registry = FactorRegistry.load_default()

    factors = audit_factors(registry, report)
    equations = audit_equations(report)
    references = audit_references(registry, report)
    audit_hardcoded_numbers(report)
    covered, total_cases, coverage_failures = quick_estimate_coverage()

    print("SCIENTIFIC READINESS REPORT")
    print("=" * 60)
    print(f"Factor database version:      {registry.version}")
    print(f"Reference database version:   {registry.references.version}")
    print()
    print(f"Factors validated:            {len(factors['validated'])}/{factors['total']}")
    print(f"Factors requiring validation: {len(factors['pending'])}")
    print(f"Validated absences:           {len(factors['validated_absence'])}")
    print(f"Factors without value:        {len(factors['without_value'])}")
    print(f"Superseded (audit only):      {len(factors['superseded'])}")
    print(
        f"Allometric equations validated: {len(equations['validated'])}/{equations['total']}"
    )
    print(
        f"Scientific references resolved: {len(references['resolved'])}/{len(references['used'])}"
    )
    print(
        f"Quick estimate coverage:      {covered}/{total_cases} "
        f"({100.0 * covered / total_cases:.0f}%)"
    )
    print(f"Hardcoded scientific numbers: {'none' if not report.blocking else 'see below'}")

    if coverage_failures:
        print()
        print("Quick estimate sem cobertura:")
        for case in coverage_failures:
            print(f"  - {case}")

    if factors["pending"]:
        print()
        print("REQUIRES_VALIDATION:")
        for fid in factors["pending"]:
            print(f"  - {fid}")

    if factors["validated_absence"]:
        print()
        print("Ausências validadas na fonte primária (não são pendências):")
        for fid in factors["validated_absence"]:
            print(f"  - {fid}")

    if report.blocking:
        print()
        print("BLOQUEANTES:")
        for msg in report.blocking:
            print(f"  ! {msg}")

    blocked = bool(report.blocking) or (args.strict and bool(factors["pending"]))
    print()
    print(f"RESULT: {'FAIL' if blocked else 'PASS'}")
    if not blocked and factors["pending"]:
        print(
            "  (PASS refere-se ao conjunto usado em produção; há pendências declaradas "
            "e recusadas pelo modo estrito)"
        )
    return 1 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
