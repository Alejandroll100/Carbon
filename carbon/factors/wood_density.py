"""Resolução de densidade básica da madeira.

Prioridade: espécie → gênero → média regional → média por tipo florestal →
fallback cientificamente defensável.

A biblioteca vem VAZIA de propósito. Densidade por espécie é um conjunto de
milhares de registros e o caminho correto é IMPORTAR uma base estruturada
(Global Wood Density Database; Tabela 4.13 do IPCC 2006 Vol.4 Cap.4 para
espécies tropicais) — não digitar valores à mão. O importador abaixo define o
contrato; enquanto nada for importado, o motor recusa em vez de arbitrar.
"""

from __future__ import annotations

from typing import Iterable, Optional

from pydantic import BaseModel

from ..models.enums import DataLevel, ValidationStatus


class WoodDensityNotFoundError(LookupError):
    """Sem densidade defensável para o táxon/contexto."""


class WoodDensityRecord(BaseModel):
    species: Optional[str] = None
    genus: Optional[str] = None
    region: Optional[str] = None
    forest_type: Optional[str] = None
    value_g_cm3: float
    n_samples: Optional[int] = None
    reference_id: str
    page_or_table: Optional[str] = None
    validation_status: ValidationStatus = ValidationStatus.REQUIRES_VALIDATION
    version: str = "0.0.0"


class WoodDensityResolution(BaseModel):
    value_g_cm3: float
    data_level: DataLevel
    matched_on: str
    record: WoodDensityRecord
    warnings: list[str] = []


class WoodDensityLibrary:
    """Biblioteca versionada e importável."""

    def __init__(self, records: Iterable[WoodDensityRecord] = (), *, version: str = "empty-0.0.0"):
        self._records = list(records)
        self.version = version

    def __len__(self) -> int:
        return len(self._records)

    def import_records(self, records: Iterable[WoodDensityRecord], *, version: str) -> int:
        """Ponto de extensão: carregar uma base estruturada com versionamento."""
        new = list(records)
        self._records.extend(new)
        self.version = version
        return len(new)

    def resolve(
        self,
        *,
        species: Optional[str] = None,
        genus: Optional[str] = None,
        region: Optional[str] = None,
        forest_type: Optional[str] = None,
    ) -> WoodDensityResolution:
        genus = genus or (species.split()[0] if species and " " in species else None)

        strategies = [
            ("species", DataLevel.SPECIES_SPECIFIC, lambda r: species and r.species == species),
            (
                "genus",
                DataLevel.SPECIES_SPECIFIC,
                # Agregado de gênero, não o registro de outra espécie do mesmo gênero.
                lambda r: genus and r.genus == genus and not r.species,
            ),
            ("region", DataLevel.REGIONAL, lambda r: region and r.region == region and not r.species),
            (
                "forest_type",
                DataLevel.BIOME_SPECIFIC,
                lambda r: forest_type and r.forest_type == forest_type and not r.species,
            ),
        ]
        for matched_on, level, predicate in strategies:
            for record in self._records:
                if predicate(record):
                    warnings = []
                    if record.validation_status == ValidationStatus.REQUIRES_VALIDATION:
                        warnings.append(
                            f"Densidade da madeira ({matched_on}) está REQUIRES_VALIDATION."
                        )
                    if matched_on in ("region", "forest_type"):
                        warnings.append(
                            f"Densidade média por {matched_on}: a equação alométrica pantropical é "
                            f"sensível a este parâmetro; usar valor por espécie quando possível."
                        )
                    return WoodDensityResolution(
                        value_g_cm3=record.value_g_cm3,
                        data_level=level,
                        matched_on=matched_on,
                        record=record,
                        warnings=warnings,
                    )

        raise WoodDensityNotFoundError(
            "Sem densidade da madeira para "
            f"espécie={species!r}, gênero={genus!r}, região={region!r}, tipo={forest_type!r}. "
            f"A biblioteca tem {len(self._records)} registro(s) (versão {self.version}). "
            "Importe uma base estruturada (Global Wood Density Database ou IPCC Vol.4 Cap.4 "
            "Tabela 4.13) ou informe wood_density_g_cm3 na medição da árvore. O motor não "
            "arbitra uma média global."
        )


#: Biblioteca default do processo. Vazia até que uma base seja importada.
DEFAULT_LIBRARY = WoodDensityLibrary()
