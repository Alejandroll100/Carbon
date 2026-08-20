"""Exemplo funcional: SAF em Registro/SP, comparação 2024 -> 2026.

Executar a partir da raiz do pacote:

    python -m examples.example_saf
"""

from __future__ import annotations

import json

from carbon.core.carbon_engine import CarbonEngine
from carbon.models.enums import (
    CalculationMode,
    EventType,
    LandUse,
    OperationalEmissionSource,
)
from carbon.models.inventory import (
    BelowgroundObservation,
    BiomassObservation,
    CarbonInventory,
    OperationalEmissionEntry,
    SoilObservation,
)
from carbon.models.land import LandEvent
from carbon.models.project import CarbonProject, Coordinates
from carbon.models.vegetation import VegetationComponent, VegetationDescription
from carbon.services.factor_service import ProjectParameter

project = CarbonProject(
    project_id="geoia-carbon-001",
    name="SAF Fazenda Teste",
    country="Brazil",
    state="São Paulo",
    municipality="Registro",
    land_use=LandUse.AGROFORESTRY,
    area_ha=125.4,
    coordinates=Coordinates(lat=-24.497, lon=-47.844),
    reference_year=2026,
    baseline_year=2024,
    climate_domain="tropical",
    biome="mata_atlantica",
)

vegetation = VegetationDescription(
    components=[
        VegetationComponent(type="tree", species="Theobroma cacao", count=12000),
        VegetationComponent(type="tree", species="Euterpe edulis", count=8000),
        VegetationComponent(type="crop", species="Musa spp."),
    ],
    age_years=6,
)


def inventory(inventory_id: str, year: int, agb_t_ha: float, oc_percent: float) -> CarbonInventory:
    return CarbonInventory(
        inventory_id=inventory_id,
        project_id=project.project_id,
        year=year,
        mode=CalculationMode.INVENTORY,
        aboveground=BiomassObservation(
            dry_biomass_t_ha=agb_t_ha,
            source="inventário de campo — parcelas permanentes",
            uncertainty_percent=14.0,
        ),
        belowground=BelowgroundObservation(
            root_to_shoot_ratio=0.24,
            root_to_shoot_source="parâmetro regional adotado pelo projeto (REQUER FONTE)",
            root_to_shoot_uncertainty_percent=35.0,
        ),
        soil=SoilObservation(
            depth_cm=30.0,
            bulk_density_g_cm3=1.18,
            organic_carbon_percent=oc_percent,
            sample_count=12,
            source="amostragem composta 0-30 cm",
            uncertainty_percent=22.0,
        ),
        vegetation=vegetation,
    )


result = CarbonEngine().calculate(
    project,
    inventory("inv-2026", 2026, 61.5, 2.42),
    baseline_inventory=inventory("inv-2024", 2024, 54.0, 2.31),
    events=[
        LandEvent(
            event_type=EventType.FIRE,
            date="2025-09-14",
            affected_area_ha=2.5,
            description="queimada acidental em faixa de bordadura",
        )
    ],
    operational_emissions=[
        OperationalEmissionEntry(
            source=OperationalEmissionSource.DIESEL, activity_amount=1800.0, activity_unit="L"
        ),
        OperationalEmissionEntry(
            source=OperationalEmissionSource.TRANSPORT,
            emission_tCO2e=3.4,
            description="frete de insumos — calculado pelo fornecedor",
        ),
    ],
    project_parameters={
        "carbon_fraction": ProjectParameter(
            value=0.47,
            unit="tC/t dry matter",
            source="valor adotado pelo projeto — pendente de conferência IPCC Tabela 4.3",
        )
    },
)

print(json.dumps(json.loads(result.model_dump_json(exclude={"audit": {"input_snapshot"}})), indent=2, ensure_ascii=False))
