"""Normalização de classificação de solos brasileiros para as classes do IPCC.

A correspondência é feita em DUAS ETAPAS, com procedências distintas:

    SiBCS (Embrapa)  --(1)-->  WRB  --(2)-->  classe IPCC da Tabela 2.3

Etapa (2) é VALIDADA: as notas de rodapé da Tabela 2.3 do IPCC 2006 Vol.4 Cap.2
listam explicitamente quais classes WRB e USDA compõem cada classe IPCC. Essas
listas estão transcritas em ``WRB_TO_IPCC``.

Etapa (1) é REQUIRES_VALIDATION: a correspondência SiBCS -> WRB precisa ser
conferida contra o Sistema Brasileiro de Classificação de Solos (Embrapa) e/ou
uma tabela de correlação publicada. Nenhuma equivalência foi inventada aqui —
cada entrada registra a classe WRB pretendida e o que falta conferir.

Consequência prática: usar uma classe do SiBCS produz um resultado marcado como
dependente de correspondência não validada, e o modo científico estrito o recusa.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from ..models.enums import IPCCSoilType, ValidationStatus

#: Transcrito das notas 1 a 6 da Tabela 2.3 (IPCC 2006 Vol.4 Cap.2).
WRB_TO_IPCC: dict[str, IPCCSoilType] = {
    # Nota 1 — HAC: solos pouco a moderadamente intemperizados, argilas 2:1
    "Leptosols": IPCCSoilType.HAC,
    "Vertisols": IPCCSoilType.HAC,
    "Kastanozems": IPCCSoilType.HAC,
    "Chernozems": IPCCSoilType.HAC,
    "Phaeozems": IPCCSoilType.HAC,
    "Luvisols": IPCCSoilType.HAC,
    "Alisols": IPCCSoilType.HAC,
    "Albeluvisols": IPCCSoilType.HAC,
    "Solonetz": IPCCSoilType.HAC,
    "Calcisols": IPCCSoilType.HAC,
    "Gypsisols": IPCCSoilType.HAC,
    "Umbrisols": IPCCSoilType.HAC,
    "Cambisols": IPCCSoilType.HAC,
    "Regosols": IPCCSoilType.HAC,
    # Nota 2 — LAC: solos muito intemperizados, argilas 1:1 e óxidos amorfos
    "Acrisols": IPCCSoilType.LAC,
    "Lixisols": IPCCSoilType.LAC,
    "Nitisols": IPCCSoilType.LAC,
    "Ferralsols": IPCCSoilType.LAC,
    "Durisols": IPCCSoilType.LAC,
    # Nota 3 — arenosos: > 70% areia e < 8% argila
    "Arenosols": IPCCSoilType.SANDY,
    # Nota 4 — espódicos
    "Podzols": IPCCSoilType.SPODIC,
    # Nota 5 — vulcânicos
    "Andosols": IPCCSoilType.VOLCANIC,
    # Nota 6 — hidromórficos
    "Gleysols": IPCCSoilType.WETLAND,
}

WRB_TO_IPCC_SOURCE = ("IPCC2006_V4_CH2", "Tabela 2.3, notas de rodapé 1 a 6")


class SoilMapping(BaseModel):
    sibcs_order: str
    wrb_equivalent: Optional[str]
    ipcc_soil_type: Optional[IPCCSoilType]
    #: Status da etapa SiBCS -> WRB (a etapa WRB -> IPCC é sempre validada).
    correspondence_status: ValidationStatus = ValidationStatus.REQUIRES_VALIDATION
    notes: Optional[str] = None


#: Ordens do SiBCS. ``wrb_equivalent`` é a correspondência PRETENDIDA, ainda
#: não conferida contra a Embrapa. Ordens sem correspondência clara ficam
#: ``None`` — o motor recusa em vez de aproximar.
SIBCS_MAPPINGS: dict[str, SoilMapping] = {
    m.sibcs_order.lower(): m
    for m in [
        SoilMapping(sibcs_order="Latossolo", wrb_equivalent="Ferralsols", ipcc_soil_type=IPCCSoilType.LAC),
        SoilMapping(sibcs_order="Argissolo", wrb_equivalent="Acrisols", ipcc_soil_type=IPCCSoilType.LAC),
        SoilMapping(sibcs_order="Nitossolo", wrb_equivalent="Nitisols", ipcc_soil_type=IPCCSoilType.LAC),
        SoilMapping(sibcs_order="Cambissolo", wrb_equivalent="Cambisols", ipcc_soil_type=IPCCSoilType.HAC),
        SoilMapping(sibcs_order="Luvissolo", wrb_equivalent="Luvisols", ipcc_soil_type=IPCCSoilType.HAC),
        SoilMapping(sibcs_order="Chernossolo", wrb_equivalent="Chernozems", ipcc_soil_type=IPCCSoilType.HAC),
        SoilMapping(sibcs_order="Vertissolo", wrb_equivalent="Vertisols", ipcc_soil_type=IPCCSoilType.HAC),
        SoilMapping(sibcs_order="Espodossolo", wrb_equivalent="Podzols", ipcc_soil_type=IPCCSoilType.SPODIC),
        SoilMapping(sibcs_order="Gleissolo", wrb_equivalent="Gleysols", ipcc_soil_type=IPCCSoilType.WETLAND),
        SoilMapping(
            sibcs_order="Neossolo",
            wrb_equivalent=None,
            ipcc_soil_type=None,
            notes=(
                "Ordem heterogênea: Quartzarênico tende a Arenosols (arenoso), Litólico a "
                "Leptosols (HAC), Flúvico a Fluvisols. Exige o SUBGRUPO, não a ordem. O motor "
                "recusa a ordem isolada."
            ),
        ),
        SoilMapping(
            sibcs_order="Plintossolo",
            wrb_equivalent=None,
            ipcc_soil_type=None,
            notes="Plinthosols não aparece nas notas da Tabela 2.3. Sem classe IPCC atribuível.",
        ),
        SoilMapping(
            sibcs_order="Organossolo",
            wrb_equivalent="Histosols",
            ipcc_soil_type=None,
            notes=(
                "Solo ORGÂNICO: fora do método de solos minerais. Usa a Equação 2.26 e a "
                "Tabela 5.6 (fator de emissão por drenagem), não SOC_REF."
            ),
        ),
        SoilMapping(
            sibcs_order="Planossolo",
            wrb_equivalent="Planosols",
            ipcc_soil_type=None,
            notes="Planosols não aparece nas notas da Tabela 2.3. Sem classe IPCC atribuível.",
        ),
    ]
}


class SoilCorrespondenceError(ValueError):
    """Classe de solo sem correspondência defensável com o esquema do IPCC."""


class SoilResolution(BaseModel):
    ipcc_soil_type: IPCCSoilType
    source_classification: str
    source_value: str
    wrb_equivalent: Optional[str] = None
    correspondence_status: ValidationStatus
    correspondence_source: Optional[str] = None
    warnings: list[str] = []


def to_ipcc_soil_type(value: str, *, classification: str = "SiBCS") -> SoilResolution:
    """Normaliza uma classe de solo para o esquema do IPCC.

    ``classification`` aceita ``"IPCC"``, ``"WRB"`` ou ``"SiBCS"``.
    """
    raw = value.strip()
    scheme = classification.strip().upper()

    if scheme == "IPCC":
        try:
            return SoilResolution(
                ipcc_soil_type=IPCCSoilType(raw),
                source_classification="IPCC",
                source_value=raw,
                correspondence_status=ValidationStatus.EXACT_CONSTANT,
                correspondence_source="entrada já no esquema do IPCC",
            )
        except ValueError as exc:
            raise SoilCorrespondenceError(
                f"'{raw}' não é classe IPCC válida. Válidas: {[s.value for s in IPCCSoilType]}"
            ) from exc

    if scheme == "WRB":
        key = raw.capitalize()
        if key not in WRB_TO_IPCC:
            raise SoilCorrespondenceError(
                f"Classe WRB '{raw}' não consta nas notas da Tabela 2.3 do IPCC. "
                f"Sem classe IPCC atribuível."
            )
        return SoilResolution(
            ipcc_soil_type=WRB_TO_IPCC[key],
            source_classification="WRB",
            source_value=key,
            wrb_equivalent=key,
            correspondence_status=ValidationStatus.VALIDATED,
            correspondence_source=" | ".join(WRB_TO_IPCC_SOURCE),
        )

    if scheme == "SIBCS":
        mapping = SIBCS_MAPPINGS.get(raw.lower())
        if mapping is None:
            raise SoilCorrespondenceError(
                f"Ordem do SiBCS desconhecida: '{raw}'. Ordens cadastradas: "
                f"{sorted(m.sibcs_order for m in SIBCS_MAPPINGS.values())}"
            )
        if mapping.ipcc_soil_type is None:
            raise SoilCorrespondenceError(
                f"'{mapping.sibcs_order}' não possui correspondência defensável com o esquema "
                f"do IPCC. {mapping.notes or ''} Informe a classe IPCC ou WRB diretamente."
            )
        return SoilResolution(
            ipcc_soil_type=mapping.ipcc_soil_type,
            source_classification="SiBCS",
            source_value=mapping.sibcs_order,
            wrb_equivalent=mapping.wrb_equivalent,
            correspondence_status=mapping.correspondence_status,
            correspondence_source=(
                f"SiBCS -> WRB: PENDENTE de conferência (EMBRAPA_SIBCS). "
                f"WRB -> IPCC: {' | '.join(WRB_TO_IPCC_SOURCE)}"
            ),
            warnings=[
                f"Correspondência SiBCS '{mapping.sibcs_order}' -> WRB "
                f"'{mapping.wrb_equivalent}' está REQUIRES_VALIDATION: não foi conferida "
                f"contra o Sistema Brasileiro de Classificação de Solos."
            ],
        )

    raise SoilCorrespondenceError(
        f"Esquema de classificação desconhecido: '{classification}'. Use IPCC, WRB ou SiBCS."
    )
