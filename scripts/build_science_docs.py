"""Gera CARBON_SCIENTIFIC_VALIDATION.md e CARBON_REFERENCES.md a partir da base.

Documentação derivada não pode divergir do código.
"""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from carbon.factors.allometric_equations import list_equations
from carbon.factors.registry import FactorRegistry
from carbon.factors.soil_classification import SIBCS_MAPPINGS, WRB_TO_IPCC_SOURCE
from carbon.models.enums import ValidationStatus

reg = FactorRegistry.load_default()
factors = sorted(reg.all(), key=lambda f: (f.category, f.factor_id))

STATUS_LABEL = {
    ValidationStatus.VALIDATED: "validated",
    ValidationStatus.REQUIRES_VALIDATION: "REQUIRES_VALIDATION",
    ValidationStatus.NO_DEFAULT_AVAILABLE: "ausência validada",
    ValidationStatus.EXACT_CONSTANT: "constante exata",
    ValidationStatus.PROJECT_SUPPLIED: "fornecido pelo projeto",
}

def applicability(f) -> str:
    bits = []
    for label, val in [
        ("clima", f.climate_region), ("regime", f.temperature_regime),
        ("umidade", f.moisture_regime), ("solo", f.soil_type), ("região", f.region),
        ("zona", f.ecological_zone), ("pool", f.pool), ("gás", f.gas),
        ("nível", f.level), ("tipo", f.factor_kind), ("ano", f.year),
        ("tipo florestal", f.forest_type), ("vegetação", f.vegetation_type),
        ("continente", f.continent), ("origem", f.origin), ("condição", f.status_condition),
        ("espécie", f.species),
    ]:
        if val:
            bits.append(f"{label}={val}")
    if f.land_use:
        bits.append("uso=" + "/".join(f.land_use))
    if f.agb_range_t_ha:
        bits.append(f"AGB {f.agb_range_t_ha[0]}–{f.agb_range_t_ha[1]} t/ha")
    return "; ".join(bits) or "genérico"

TEST_MAP = {
    "carbon_fraction": "test_carbon_fraction_is_not_uniform_across_pools",
    "root_to_shoot_ratio": "test_ipcc_ch4_worked_example_biomass_gain / test_root_shoot_stratum_does_not_apply_outside_its_agb_range",
    "soil_organic_carbon_reference": "test_soc_ref_tropical_values_match_table_23 / test_ipcc_ch5_worked_example_soc_initial_stock",
    "soil_stock_change_factor": "test_ipcc_ch5_worked_example_soc_final_stock_and_annual_change",
    "agb_carbon_density": "test_ipcc_ch5_worked_example_perennial_biomass",
    "agb_biomass_density": "test_quick_estimate_runs_for_brazilian_agroforestry",
    "agb_carbon_year1_after_conversion": "—",
    "litter_carbon_stock": "—",
    "deadwood_carbon_stock": "test_validated_absence_is_distinct_from_pending_validation",
    "organic_soil_emission_factor": "test_organic_soil_emission_factors_match_table_56",
    "operational_emission_factor": "test_electricity_factor_is_year_specific_and_never_extrapolated",
    "agb_net_growth": "—",
}

lines = [
    "# GEØ.IA CARBON — VALIDAÇÃO CIENTÍFICA",
    "",
    f"Base de fatores `{reg.version}` · bibliografia `{reg.references.version}`.",
    "",
    "**Documento gerado** por `scripts/build_science_docs.py` a partir de",
    "`carbon/factors/defaults.json`. Não editar à mão.",
    "",
    "Validar significa: localizar a fonte primária, ler o valor no documento,",
    "conferir unidade, aplicabilidade, domínio climático, tipo de vegetação,",
    "faixa de biomassa e incerteza, e registrar tabela/página e data. Trocar a",
    "flag sem essa leitura não é validação.",
    "",
    "## Sumário",
    "",
    f"| Situação | Fatores |",
    f"| --- | --- |",
]
by_status = {}
for f in factors:
    by_status.setdefault(f.validation_status, []).append(f)
for st, items in sorted(by_status.items(), key=lambda kv: kv[0].value):
    lines.append(f"| {STATUS_LABEL[st]} | {len(items)} |")
lines += ["", f"| **Total** | **{len(factors)}** |", ""]

current = None
for f in factors:
    if f.category != current:
        current = f.category
        lines += ["", f"## `{current}`", "",
                  "| Factor | Valor | Unidade | Aplicabilidade | Fonte primária | Tabela/página | Incerteza | Status | Testes |",
                  "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    value = "—" if f.value is None else f"{f.value:g}"
    if f.uncertainty_percent is not None:
        unc = f"±{f.uncertainty_percent:g}%"
    elif f.uncertainty_absolute is not None:
        unc = f"SD {f.uncertainty_absolute:g} {f.unit}"
    else:
        unc = "—"
    ref = f.reference_id or "—"
    if f.is_superseded:
        status_label = f"SUPERADO por {f.superseded_by}"
    else:
        status_label = STATUS_LABEL[f.validation_status]
    lines.append(
        f"| `{f.factor_id}` | {value} | {f.unit} | {applicability(f)} | {ref} | "
        f"{f.page_or_table or '—'} | {unc} | {status_label} | "
        f"{TEST_MAP.get(f.category, '—')} |"
    )

lines += ["", "## Equações alométricas", "",
          "| Equação | Fórmula | Coeficientes | Faixa de DAP | Verificado | Não verificado | Status |",
          "| --- | --- | --- | --- | --- | --- | --- |"]
for e in list_equations():
    if e.equation_id == "PROJECT_SPECIFIC_PLACEHOLDER":
        continue
    coef = ", ".join(f"{k}={v}" for k, v in e.coefficients.items()) or "—"
    rng = f"{e.dbh_range_cm[0]}–{e.dbh_range_cm[1] or 'sem teto declarado'} cm" if e.dbh_range_cm else "—"
    lines.append(
        f"| `{e.equation_id}` | `{e.equation}` | {coef} | {rng} | "
        f"{'; '.join(e.verified_metadata) or '—'} | {'; '.join(e.unverified_items) or '—'} | "
        f"{e.validation_status.value} |"
    )

lines += ["", "## Normalização de solos brasileiros", "",
          f"Etapa WRB → IPCC: **validada** ({WRB_TO_IPCC_SOURCE[1]}).",
          "Etapa SiBCS → WRB: **REQUIRES_VALIDATION** — pendente de conferência contra a Embrapa.",
          "", "| Ordem SiBCS | WRB pretendido | Classe IPCC | Observação |", "| --- | --- | --- | --- |"]
for m in sorted(SIBCS_MAPPINGS.values(), key=lambda m: m.sibcs_order):
    lines.append(
        f"| {m.sibcs_order} | {m.wrb_equivalent or '—'} | "
        f"{m.ipcc_soil_type.value if m.ipcc_soil_type else 'RECUSADO'} | {m.notes or '—'} |"
    )
(ROOT / "CARBON_SCIENTIFIC_VALIDATION.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

ACCESS = {
    "full_text_verified": "texto integral lido",
    "partial_text_verified": "texto parcialmente lido",
    "metadata_only": "apenas metadados",
    "not_accessed": "não consultado diretamente",
}
used = {f.reference_id for f in factors if f.reference_id}
# Referências citadas pela CAMADA DE SENSORIAMENTO REMOTO. Elas não têm
# fator associado por construção: um dataset do Earth Engine é fonte de
# OBSERVAÇÃO, não de fator científico. Sem esta distinção o documento diria
# "registrada mas ainda não usada" para uma referência que é usada o tempo todo.
from carbon.services.gee_datasets import ALL_DATASETS
remote_sensing_used = {d.reference_id for d in ALL_DATASETS if d.reference_id}
DATASET_BY_REFERENCE = {d.reference_id: d for d in ALL_DATASETS if d.reference_id}
ref_lines = ["# GEØ.IA CARBON — BIBLIOGRAFIA", "",
             f"Versão `{reg.references.version}`. Fonte de verdade: `carbon/factors/references.json`.",
             "Documento gerado por `scripts/build_science_docs.py`.", "",
             "`Nível de acesso` registra o que foi de fato lido — distinção que",
             "importa: um valor lido no documento primário não tem o mesmo peso",
             "que um valor conhecido apenas por citação secundária.", ""]
for r in sorted(reg.references.all(), key=lambda r: r.reference_id):
    n = sum(1 for f in factors if f.reference_id == r.reference_id)
    ref_lines += [
        f"## `{r.reference_id}`", "",
        f"**{r.title}**", "",
        f"- Organização: {r.organization or '—'}",
        f"- Ano: {r.year or '—'}",
        f"- Documento: {r.document or '—'}" + (f", capítulo {r.chapter}" if r.chapter else ""),
        f"- URL: {r.url or '—'}",
        f"- DOI: {r.doi or '—'}",
        f"- Nível de acesso: **{ACCESS[r.access_level]}**"
        + (f" (em {r.accessed_at})" if r.accessed_at else ""),
        f"- Fatores que a citam: {n}"
        + (
            ""
            if r.reference_id in used
            else (
                "  ← fonte de observação geoespacial (não gera fator)"
                if r.reference_id in remote_sensing_used
                else "  ← registrada mas ainda não usada"
            )
        ),
        "",
    ]
    dataset = DATASET_BY_REFERENCE.get(r.reference_id)
    if dataset is not None:
        ref_lines += [
            f"- Dataset Earth Engine: `{dataset.dataset_id}`"
            + (f" (v{dataset.version})" if dataset.version else ""),
            f"- Variáveis: {', '.join(dataset.variables) or '—'}",
            f"- Unidade: {dataset.units or '—'}",
            f"- Resolução: {dataset.spatial_resolution_m or '—'} m",
            f"- Período: {dataset.temporal_start} .. {dataset.temporal_end}",
            f"- Filtros de qualidade: {'; '.join(dataset.quality_filters) or '—'}",
            "",
        ]
        for limitation in dataset.limitations:
            ref_lines += [f"  - limitação: {limitation}"]
        for pending in dataset.unverified_items:
            ref_lines += [f"  - NÃO CONFERIDO: {pending}"]
        if dataset.limitations or dataset.unverified_items:
            ref_lines += [""]
    if r.notes:
        ref_lines += [f"> {r.notes}", ""]
(ROOT / "CARBON_REFERENCES.md").write_text("\n".join(ref_lines) + "\n", encoding="utf-8")
print("docs gerados")
