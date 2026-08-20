"""Serviço de inventário florestal: parcelas -> AGB do projeto.

A extrapolação parcela -> projeto é uma modelagem, não uma medição. Por isso o
resultado é marcado ``modelled`` e a incerteza reportada é apenas a de
AMOSTRAGEM (erro padrão entre parcelas). O erro do modelo alométrico NÃO está
incluído — isso é declarado explicitamente.
"""

from __future__ import annotations

import math
from typing import Optional, Sequence

from ..factors.allometric_equations import (
    EquationNotFoundError,
    MissingVariableError,
    estimate_tree_biomass,
    get_equation,
)
from ..models.enums import DataLevel, EstimationType
from ..models.inventory import Plot
from ..models.project import CarbonProject
from ..models.provenance import TracedValue
from ..utils.units import KG_PER_T, M2_PER_HA

DRY_MATTER_UNIT = "t dry matter"
SAMPLING_UNCERTAINTY_METHOD = "erro padrão entre parcelas x 1.96 (apenas amostragem)"


#: Escore z para intervalo de confiança de 95% (distribuição normal).
#: Constante estatística, não fator científico.
Z_SCORE_95 = 1.96


def plot_biomass_density(
    plot: Plot,
    *,
    default_equation_id: Optional[str] = None,
    default_wood_density: Optional[float] = None,
) -> tuple[float, list[str], list[str]]:
    """Retorna (densidade t m.s./ha, equações usadas, avisos)."""
    total_kg = 0.0
    equations: list[str] = []
    warnings: list[str] = []

    for tree in plot.trees:
        if not tree.alive:
            continue
        equation_id = tree.equation_id or default_equation_id
        if equation_id is None:
            raise MissingVariableError(
                f"Árvore {tree.tree_id or '?'} da parcela {plot.plot_id} sem equation_id. "
                "A escolha da equação alométrica é decisão metodológica explícita."
            )
        result = estimate_tree_biomass(
            dbh_cm=tree.dbh_cm,
            height_m=tree.height_m,
            wood_density_g_cm3=tree.wood_density_g_cm3 or default_wood_density,
            equation_id=equation_id,
        )
        total_kg += float(result["biomass_kg"])
        if equation_id not in equations:
            equations.append(equation_id)
        for w in result["warnings"]:  # type: ignore[union-attr]
            if w not in warnings:
                warnings.append(w)

    plot_area_ha = plot.area_m2 / M2_PER_HA
    density_t_ha = (total_kg / KG_PER_T) / plot_area_ha
    return density_t_ha, equations, warnings


def aboveground_from_plots(
    project: CarbonProject,
    plots: Sequence[Plot],
    *,
    default_equation_id: Optional[str] = None,
    default_wood_density: Optional[float] = None,
) -> TracedValue:
    if not plots:
        return TracedValue.not_available(DRY_MATTER_UNIT, "Nenhuma parcela informada.")

    densities: list[float] = []
    weights: list[float] = []
    equations: list[str] = []
    warnings: list[str] = []
    tree_count = 0

    for plot in plots:
        try:
            density, eqs, warns = plot_biomass_density(
                plot,
                default_equation_id=default_equation_id,
                default_wood_density=default_wood_density,
            )
        except (MissingVariableError, EquationNotFoundError) as exc:
            return TracedValue.not_available(
                DRY_MATTER_UNIT, f"Inventário não processável: {exc}"
            )
        densities.append(density)
        weights.append(plot.area_m2)
        tree_count += len([t for t in plot.trees if t.alive])
        for e in eqs:
            if e not in equations:
                equations.append(e)
        for w in warns:
            if w not in warnings:
                warnings.append(w)

    total_weight = sum(weights)
    mean_density = sum(d * w for d, w in zip(densities, weights)) / total_weight

    uncertainty_percent: Optional[float] = None
    if len(densities) >= 2 and mean_density > 0:
        mean_simple = sum(densities) / len(densities)
        variance = sum((d - mean_simple) ** 2 for d in densities) / (len(densities) - 1)
        std_error = math.sqrt(variance / len(densities))
        uncertainty_percent = (Z_SCORE_95 * std_error / mean_density) * 100.0
    else:
        warnings.append(
            "Menos de 2 parcelas: erro amostral não estimável. Incerteza não reportada."
        )

    explicit_expansion = [p.expansion_factor for p in plots if p.expansion_factor is not None]
    if explicit_expansion:
        total = sum(
            (d * (p.area_m2 / M2_PER_HA)) * (p.expansion_factor or 1.0)
            for d, p in zip(densities, plots)
        )
        expansion_note = "Extrapolação por fator de expansão informado por parcela."
    else:
        total = mean_density * project.area_ha
        expansion_note = (
            "Extrapolação pela densidade média ponderada por área amostrada x área do projeto. "
            f"Intensidade amostral: {total_weight / M2_PER_HA:.4f} ha em {project.area_ha:g} ha."
        )

    warnings.append(
        "Incerteza reportada cobre apenas erro de amostragem entre parcelas; "
        "não inclui o erro do modelo alométrico nem o erro de medição de DBH/altura."
    )

    return TracedValue(
        value=total,
        unit=DRY_MATTER_UNIT,
        estimation_type=EstimationType.MODELLED,
        data_level=DataLevel.MEASURED,
        source="field_inventory",
        tier=3,
        uncertainty_percent=uncertainty_percent,
        equations_used=equations,
        inputs={
            "plots": len(plots),
            "trees": tree_count,
            "sampled_area_ha": total_weight / M2_PER_HA,
            "mean_density_t_ha": mean_density,
            "project_area_ha": project.area_ha,
        },
        notes=[expansion_note, *warnings],
    )


def equation_audit(equation_ids: Sequence[str]) -> list[dict]:
    trail: list[dict] = []
    for eid in dict.fromkeys(equation_ids):
        try:
            meta = get_equation(eid)
        except EquationNotFoundError:
            continue  # string de fórmula documental, não id de equação cadastrada
        trail.append(
            {
                "equation_id": meta.equation_id,
                "name": meta.name,
                "equation": meta.equation,
                "version": meta.version,
                "source": meta.source,
                "validation_status": meta.validation_status.value,
            }
        )
    return trail
