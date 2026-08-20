"""Adapter: observação de sensoriamento remoto -> ``CarbonInventory``.

    RemoteSensingObservation -> RemoteSensingInventoryAdapter -> CarbonInventory
                             -> CarbonEngine

O ``CarbonEngine`` continua sem saber que o Earth Engine existe. Ele recebe um
inventário com uma observação de biomassa aérea marcada ``remote_sensing`` e
aplica a mesma matemática de sempre.

Duas regras de segurança implementadas aqui:

1. **Hierarquia de fontes** (§16): medição de campo > modelo calibrado do
   projeto > GEDI válido > raster de biomassa validado > default IPCC >
   indisponível. Uma fonte mais fraca nunca substitui uma mais forte em
   silêncio — a decisão e os níveis recusados ficam registrados.
2. **A fração de carbono não é aplicada aqui.** O adapter entrega MATÉRIA
   SECA. Quem converte para carbono é o ``biomass_engine``, uma única vez.
"""

from __future__ import annotations

from typing import Optional

from ..models.enums import CalculationMode, EstimationType
from ..models.inventory import BiomassObservation, CarbonInventory
from ..models.remote_sensing import (
    BiomassRemoteObservation,
    BiomassSourceDecision,
    BiomassSourceLevel,
    LandCoverConsistency,
    RemoteSensingBundle,
    SamplingSupport,
)
from .gee_datasets import GEDI_L4A

#: Incerteza acima deste percentual não cabe no campo do modelo de entrada
#: (``BiomassObservation.uncertainty_percent`` é limitado a 100). Nesse caso o
#: valor NÃO é truncado para caber: ele deixa de ser propagado e permanece
#: visível na proveniência, com aviso.
MAX_REPRESENTABLE_UNCERTAINTY_PERCENT = 100.0


def select_biomass_source(
    *,
    biomass: Optional[BiomassRemoteObservation],
    consistency: Optional[LandCoverConsistency] = None,
    field_measurement_available: bool = False,
    calibrated_model_available: bool = False,
) -> BiomassSourceDecision:
    """Aplica a hierarquia de fontes e devolve a decisão auditável."""
    rejected: list[dict] = []

    if field_measurement_available:
        rejected.append(
            {
                "level": BiomassSourceLevel.GEDI_VALID_OBSERVATIONS.value,
                "reason": "Medição de campo disponível tem precedência sobre sensoriamento remoto.",
            }
        )
        return BiomassSourceDecision(
            selected=BiomassSourceLevel.FIELD_MEASUREMENT,
            reason="Inventário de campo presente: nenhuma observação remota o substitui.",
            rejected=rejected,
        )

    if calibrated_model_available:
        return BiomassSourceDecision(
            selected=BiomassSourceLevel.PROJECT_CALIBRATED_MODEL,
            reason="Modelo calibrado do projeto tem precedência sobre o produto global.",
            rejected=rejected,
        )

    if consistency is not None and consistency.blocking:
        rejected.append(
            {
                "level": BiomassSourceLevel.GEDI_VALID_OBSERVATIONS.value,
                "reason": consistency.message or "Incoerência bloqueante de cobertura da terra.",
            }
        )
        return BiomassSourceDecision(
            selected=BiomassSourceLevel.UNAVAILABLE,
            reason=(
                "Incoerência entre uso da terra declarado e cobertura observada: "
                "estimativa de biomassa remota recusada."
            ),
            rejected=rejected,
        )

    if biomass is not None and biomass.available:
        if biomass.support is SamplingSupport.USABLE:
            return BiomassSourceDecision(
                selected=BiomassSourceLevel.GEDI_VALID_OBSERVATIONS,
                reason=(
                    f"GEDI L4A com suporte amostral utilizável "
                    f"({biomass.sample_count} footprints)."
                ),
                rejected=rejected,
            )
        rejected.append(
            {
                "level": BiomassSourceLevel.GEDI_VALID_OBSERVATIONS.value,
                "reason": (
                    f"insufficient GEDI sampling: suporte '{biomass.support.value}' "
                    f"({biomass.sample_count} footprints). A média não é extrapolada "
                    "para a AOI."
                ),
            }
        )
    else:
        rejected.append(
            {
                "level": BiomassSourceLevel.GEDI_VALID_OBSERVATIONS.value,
                "reason": (biomass.reason if biomass else "Sem observação de biomassa remota."),
            }
        )

    rejected.append(
        {
            "level": BiomassSourceLevel.VALIDATED_BIOMASS_RASTER.value,
            "reason": "Nenhum raster de biomassa calibrado e validado está registrado no motor.",
        }
    )
    return BiomassSourceDecision(
        selected=BiomassSourceLevel.IPCC_REGIONAL_DEFAULT,
        reason=(
            "Sem biomassa remota utilizável. O Carbon Engine decide entre fator "
            "default aplicável e indisponibilidade — a camada geoespacial não "
            "arbitra valor."
        ),
        rejected=rejected,
        delegated_to_engine=True,
    )


class RemoteSensingInventoryAdapter:
    """Constrói ``CarbonInventory`` a partir do pacote de observações."""

    def build_aboveground_observation(
        self, biomass: BiomassRemoteObservation
    ) -> tuple:
        """Devolve (observação de AGB, avisos). Nunca devolve zero por ausência."""
        warnings: list[str] = []
        if not biomass.available or biomass.agb_density_t_ha is None:
            return None, [biomass.reason or "Biomassa remota indisponível."]

        uncertainty = biomass.sampling_uncertainty_percent
        if uncertainty is not None and uncertainty > MAX_REPRESENTABLE_UNCERTAINTY_PERCENT:
            warnings.append(
                f"Incerteza amostral de {uncertainty:.1f}% excede o máximo representável "
                "no inventário (100%). NÃO foi truncada: deixou de ser propagada e "
                "permanece registrada na proveniência da observação."
            )
            uncertainty = None

        observation = BiomassObservation(
            dry_biomass_t_ha=biomass.agb_density_t_ha,
            estimation_type=EstimationType.REMOTE_SENSING,
            source=(
                f"{GEDI_L4A.dataset_id} | {GEDI_L4A.name} v{GEDI_L4A.version} | "
                f"agbd mean sobre {biomass.sample_count} footprints"
            ),
            uncertainty_percent=uncertainty,
        )
        warnings.extend(biomass.warnings)
        return observation, warnings

    def to_inventory(
        self,
        bundle: RemoteSensingBundle,
        *,
        project_id: str,
        inventory_id: str,
        year: int,
        biomass: Optional[BiomassRemoteObservation] = None,
    ) -> tuple:
        """Inventário com APENAS o pool que foi realmente observado.

        Madeira morta, serapilheira e solo não são observáveis por estes
        produtos e permanecem ausentes — o motor os reportará como ``null``,
        nunca como zero.
        """
        source = biomass if biomass is not None else bundle.biomass
        aboveground, warnings = self.build_aboveground_observation(source)
        inventory = CarbonInventory(
            inventory_id=inventory_id,
            project_id=project_id,
            year=year,
            mode=CalculationMode.INVENTORY if aboveground else CalculationMode.QUICK_ESTIMATE,
            aboveground=aboveground,
            notes=(
                "Inventário construído por sensoriamento remoto (GEDI L4A). "
                "Pools de madeira morta, serapilheira e solo NÃO são observáveis "
                "por este produto e permanecem indisponíveis."
            ),
        )
        return inventory, warnings
