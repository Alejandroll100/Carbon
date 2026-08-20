"""Interface de sensoriamento remoto (P2) — sem implementação numérica agora.

Regra §26: NDVI não é carbono. Nenhum índice de vegetação é convertido
diretamente em tonelada de carbono sem modelo calibrado e validado. Os métodos
abaixo definem o contrato; o provider default declara indisponibilidade em vez
de devolver número.
"""

from __future__ import annotations

from typing import Optional, Protocol

from ..models.provenance import TracedValue

SUPPORTED_SOURCES = (
    "sentinel-2",
    "landsat",
    "gedi",
    "dem",
    "land_cover",
    "vegetation_indices",
    "canopy_height",
    "biomass_raster",
)


class RemoteSensingCarbonProvider(Protocol):
    """Contrato para provedores de dados geoespaciais."""

    def estimate_biomass(self, *, geometry: dict, year: int) -> TracedValue: ...

    def estimate_canopy(self, *, geometry: dict, year: int) -> TracedValue: ...

    def estimate_land_cover(self, *, geometry: dict, year: int) -> dict: ...

    def estimate_change(self, *, geometry: dict, baseline_year: int, current_year: int) -> TracedValue: ...


class NullRemoteSensingProvider:
    """Provider default: declara indisponibilidade, nunca inventa valor."""

    name = "null_provider"

    def _unavailable(self, what: str) -> TracedValue:
        return TracedValue.not_available(
            "tC",
            f"{what}: provider de sensoriamento remoto não configurado (P2). "
            "Índice de vegetação não é convertido em carbono sem modelo calibrado.",
        )

    def estimate_biomass(self, *, geometry: dict, year: int) -> TracedValue:
        return self._unavailable("estimate_biomass")

    def estimate_canopy(self, *, geometry: dict, year: int) -> TracedValue:
        return self._unavailable("estimate_canopy")

    def estimate_land_cover(self, *, geometry: dict, year: int) -> dict:
        return {"available": False, "reason": "provider não configurado (P2)"}

    def estimate_change(
        self, *, geometry: dict, baseline_year: int, current_year: int
    ) -> TracedValue:
        return self._unavailable("estimate_change")


def vegetation_index_role(index_name: str, value: Optional[float] = None) -> dict:
    """Documenta o papel admissível de um índice de vegetação.

    Usos permitidos: indicador de vegetação, indicador de mudança, feature de
    modelo. Uso proibido: conversão direta em carbono.
    """
    return {
        "index": index_name,
        "value": value,
        "allowed_uses": ["vegetation_indicator", "change_indicator", "model_feature"],
        "forbidden_uses": ["direct_carbon_conversion"],
        "carbon_equivalent": None,
        "note": "Índice espectral não é estoque de carbono.",
    }
