"""§29 — nenhum caminho de código converte índice espectral em carbono.

Este teste não exercita comportamento: ele LÊ a árvore sintática de todo o
pacote ``carbon`` e falha se alguém, algum dia, escrever

    carbon = ndvi * constante
    biomass = evi * fator_magico

Um teste de comportamento só cobre os caminhos que alguém lembrou de testar.
Um teste estático cobre o repositório inteiro, inclusive código futuro.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

CARBON_DIR = Path(__file__).resolve().parents[1]
SKIP_DIRS = {"tests", "__pycache__"}

#: Nomes que denotam índice espectral.
SPECTRAL_PATTERN = re.compile(
    r"(?:^|_)(ndvi|evi|nbr|ndmi|ndwi|savi|spectral_index|vegetation_index)(?:$|_)",
    re.IGNORECASE,
)
#: Nomes que denotam quantidade de carbono ou biomassa.
CARBON_PATTERN = re.compile(
    r"(?:^|_)(carbon|biomass|agb|bgb|tco2e?|tc|co2e?|stock)(?:$|_)", re.IGNORECASE
)


def python_files() -> list[Path]:
    return [
        path
        for path in sorted(CARBON_DIR.rglob("*.py"))
        if not any(part in SKIP_DIRS for part in path.parts)
    ]


def _names_in(node: ast.AST) -> list[str]:
    found: list[str] = []
    for inner in ast.walk(node):
        if isinstance(inner, ast.Name):
            found.append(inner.id)
        elif isinstance(inner, ast.Attribute):
            found.append(inner.attr)
        elif isinstance(inner, ast.Constant) and isinstance(inner.value, str):
            # Chave de dicionário: obs["ndvi"] * 0.5 também é conversão.
            found.append(inner.value)
    return found


def _target_names(target: ast.AST) -> list[str]:
    names: list[str] = []
    for inner in ast.walk(target):
        if isinstance(inner, ast.Name):
            names.append(inner.id)
        elif isinstance(inner, ast.Attribute):
            names.append(inner.attr)
    return names


def test_no_assignment_of_carbon_from_a_spectral_index():
    """Nenhuma variável de carbono/biomassa é atribuída a partir de um índice."""
    violations: list[str] = []
    for path in python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                targets = [n for t in node.targets for n in _target_names(t)]
                value_node = node.value
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                targets = _target_names(node.target)
                value_node = node.value
            else:
                continue
            if not any(CARBON_PATTERN.search(name) for name in targets):
                continue
            if any(SPECTRAL_PATTERN.search(name) for name in _names_in(value_node)):
                violations.append(
                    f"{path.relative_to(CARBON_DIR.parent)}:{node.lineno}: "
                    f"{targets} derivado de índice espectral"
                )
    assert not violations, "Conversão índice -> carbono detectada:\n" + "\n".join(violations)


def test_no_arithmetic_between_a_spectral_index_and_a_constant():
    """``ndvi * 0.47`` e equivalentes não existem em lugar nenhum do pacote."""
    violations: list[str] = []
    for path in python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.BinOp):
                continue
            if not isinstance(node.op, (ast.Mult, ast.Div, ast.Pow)):
                continue
            operands = [node.left, node.right]
            has_index = any(
                any(SPECTRAL_PATTERN.search(name) for name in _names_in(side))
                for side in operands
            )
            has_number = any(
                isinstance(side, ast.Constant) and isinstance(side.value, (int, float))
                for side in operands
            )
            if has_index and has_number:
                violations.append(
                    f"{path.relative_to(CARBON_DIR.parent)}:{node.lineno}: "
                    "índice espectral multiplicado/dividido por constante"
                )
    assert not violations, "Aritmética proibida com índice espectral:\n" + "\n".join(
        violations
    )


def test_vegetation_indicators_model_has_no_carbon_field():
    """A proibição também é estrutural: o modelo não tem onde guardar carbono."""
    from carbon.models.remote_sensing import VegetationIndicators

    fields = set(VegetationIndicators.model_fields)
    for field in fields:
        if field == "carbon_equivalent":
            continue
        assert not CARBON_PATTERN.search(field), (
            f"Campo '{field}' em VegetationIndicators sugere quantidade de carbono."
        )
    assert VegetationIndicators().carbon_equivalent is None


def test_vegetation_index_role_forbids_direct_conversion():
    from carbon.services.geospatial_service import vegetation_index_role

    for index in ("ndvi", "evi", "nbr", "ndmi"):
        role = vegetation_index_role(index, 0.8)
        assert role["carbon_equivalent"] is None
        assert "direct_carbon_conversion" in role["forbidden_uses"]
        assert "model_feature" in role["allowed_uses"]


def test_gedi_path_is_biomass_not_a_spectral_index():
    """A única fonte de biomassa remota é lidar, e ela é declarada como tal."""
    from carbon.services.gee_datasets import GEDI_L4A, SENTINEL2_SR

    assert "biomassa" in GEDI_L4A.purpose.lower()
    assert GEDI_L4A.units.startswith("Mg/ha")
    assert "carbono" not in SENTINEL2_SR.purpose.lower()
    assert any(
        "não é estoque de carbono" in limitation.lower()
        for limitation in SENTINEL2_SR.limitations
    )


@pytest.mark.parametrize(
    "forbidden_source",
    [
        "carbon_t = ndvi * 100.0",
        "biomass_total = evi * 250.0",
        "agb_t_ha = obs['ndvi'] * 3.0",
    ],
)
def test_the_guard_actually_catches_violations(forbidden_source: str, tmp_path: Path):
    """Sanidade do próprio teste: ele reprova o padrão que promete reprovar."""
    tree = ast.parse(forbidden_source)
    caught = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets = [n for t in node.targets for n in _target_names(t)]
            if any(CARBON_PATTERN.search(name) for name in targets) and any(
                SPECTRAL_PATTERN.search(name) for name in _names_in(node.value)
            ):
                caught = True
    assert caught, "O guard não detectaria esta violação — o guard está quebrado."
