"""Orquestração da análise geoespacial de carbono.

    lat/lon ou polígono -> AOI -> Google Earth Engine -> observações
    rastreáveis -> CarbonInventory -> CarbonEngine existente

O ``CarbonEngine`` NÃO é alterado nem reescrito: ele recebe projeto e
inventário como sempre. Toda a lógica geoespacial vive antes dele.

Nota de arquitetura (desvio deliberado e declarado): o escopo sugeria
``carbon_engine.calculate_from_coordinates(...)``. Isso colocaria a camada
geoespacial dentro do núcleo científico e violaria a regra de que o motor
precisa continuar testável sem internet e sem o SDK do Earth Engine. O método
foi implementado aqui, em ``GeospatialCarbonService.calculate_from_coordinates``,
com a mesma assinatura conceitual.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from ..core.carbon_engine import CarbonEngine, CarbonEngineConfig
from ..factors.registry import FactorRegistry
from ..models.enums import IPCCClimateRegion, IPCCSoilType, LandUse
from ..models.project import CarbonProject, Coordinates, Geometry
from ..models.remote_sensing import (
    AreaOfInterest,
    AreaSource,
    BiomassSourceLevel,
    RemoteSensingBundle,
    SamplingSupport,
)
from ..models.result import DISCLAIMER
from ..version import ENGINE_VERSION, REMOTE_SENSING_LAYER_VERSION
from .gee_client import GEEQueryError
from .gee_datasets import dataset_catalog
from .gee_provider import GoogleEarthEngineCarbonProvider, observe_all
from .geometry_service import build_aoi
from .remote_sensing_adapter import RemoteSensingInventoryAdapter, select_biomass_source

#: Rubrica do SUPORTE DE SENSORIAMENTO REMOTO (0-100).
#:
#: É um indicador SEPARADO do ``confidence_score`` do motor e do
#: ``data_quality_score``. Não é probabilidade, não é certificação e não
#: substitui a incerteza estatística. Mede se a OBSERVAÇÃO é boa — não se o
#: resultado de carbono é bom.
REMOTE_SENSING_CONFIDENCE_WEIGHTS = {
    "sampling_support": 30.0,
    "sampled_fraction_of_aoi": 15.0,
    "uncertainty_declared": 15.0,
    "temporal_proximity": 15.0,
    "cloud_conditions": 10.0,
    "land_cover_consistency": 15.0,
}
SUPPORT_SCORE = {
    SamplingSupport.USABLE: 1.0,
    SamplingSupport.LOW_SUPPORT: 0.5,
    SamplingSupport.VERY_LOW_SUPPORT: 0.2,
    SamplingSupport.UNAVAILABLE: 0.0,
}
#: Teto quando o suporte amostral não é utilizável: satélite não compra confiança.
NON_USABLE_SUPPORT_CAP = 40
#: Fração da AOI efetivamente amostrada que já satura o componente. O GEDI é
#: amostragem por transecto: 1% da AOI coberta por footprints já é bom.
SAMPLED_FRACTION_SATURATION = 0.01
#: Nota do componente temporal quando a observação efetiva caiu em ano
#: diferente do solicitado. Limiar operacional GEØ.IA.
TEMPORAL_MISMATCH_SCORE = 0.6

RESULT_TYPE = "remote_sensing_supported_carbon_estimate"


class GeospatialAnalysisInput(BaseModel):
    """Entrada da análise por coordenada ou geometria."""

    lat: Optional[float] = None
    lon: Optional[float] = None
    area_ha: Optional[float] = Field(default=None, gt=0)
    geometry: Optional[dict] = None
    current_year: int
    baseline_year: Optional[int] = None
    land_use: LandUse = LandUse.OTHER
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    country: Optional[str] = None
    state: Optional[str] = None
    municipality: Optional[str] = None
    climate_region: Optional[IPCCClimateRegion] = None
    soil_type: Optional[IPCCSoilType] = None
    region: Optional[str] = None
    ecological_zone: Optional[str] = None
    continent: Optional[str] = None
    forest_origin: Optional[str] = None
    forest_status: Optional[str] = None
    strict_factor_validation: bool = False
    window_expansion_months: int = Field(default=0, ge=0, le=12)


class GeospatialCarbonService:
    """Junta provider geoespacial, adapter e Carbon Engine."""

    def __init__(
        self,
        provider: GoogleEarthEngineCarbonProvider,
        *,
        registry: Optional[FactorRegistry] = None,
        adapter: Optional[RemoteSensingInventoryAdapter] = None,
    ) -> None:
        self.provider = provider
        self.registry = registry or FactorRegistry.load_default()
        self.adapter = adapter or RemoteSensingInventoryAdapter()

    # -- API conceitual do escopo ---------------------------------------------

    def calculate_from_coordinates(
        self,
        *,
        lat: float,
        lon: float,
        area_ha: float,
        year: int,
        baseline_year: Optional[int] = None,
        land_use: LandUse = LandUse.OTHER,
        **extra,
    ) -> dict:
        return self.analyze(
            GeospatialAnalysisInput(
                lat=lat,
                lon=lon,
                area_ha=area_ha,
                current_year=year,
                baseline_year=baseline_year,
                land_use=land_use,
                **extra,
            )
        )

    # -- pipeline --------------------------------------------------------------

    def build_aoi(self, request: GeospatialAnalysisInput) -> AreaOfInterest:
        aoi = build_aoi(
            lat=request.lat,
            lon=request.lon,
            area_ha=request.area_ha,
            geometry=request.geometry,
        )
        if aoi.area_source is AreaSource.LOCAL_SPHERICAL_APPROXIMATION:
            try:
                geodesic_ha = self.provider.client.geodesic_area_ha(aoi.geojson)
            except (GEEQueryError, AttributeError, NotImplementedError) as exc:
                aoi.notes.append(
                    f"Área geodésica do Earth Engine indisponível ({exc}); mantida a "
                    "aproximação esférica local."
                )
            else:
                aoi.notes.append(
                    f"Área geodésica do Earth Engine: {geodesic_ha:.4f} ha "
                    f"(aproximação local era {aoi.area_ha:.4f} ha)."
                )
                aoi.area_ha = geodesic_ha
                aoi.area_source = AreaSource.GEODESIC_COMPUTED_GEE
        return aoi

    def build_project(
        self, request: GeospatialAnalysisInput, aoi: AreaOfInterest
    ) -> CarbonProject:
        return CarbonProject(
            project_id=request.project_id or f"geoia-carbon-gee-{aoi.geometry_hash[:8]}",
            name=request.project_name or "Análise geoespacial GEØ.IA Carbon",
            country=request.country,
            state=request.state,
            municipality=request.municipality,
            land_use=request.land_use,
            area_ha=aoi.area_ha,
            coordinates=Coordinates(lat=aoi.lat, lon=aoi.lon),
            geometry=Geometry(
                geometry_type="polygon",
                reference=aoi.geometry_source.value,
                geojson=aoi.geojson,
            ),
            reference_year=request.current_year,
            baseline_year=request.baseline_year,
            climate_region=request.climate_region,
            soil_type=request.soil_type,
            region=request.region,
            ecological_zone=request.ecological_zone,
            continent=request.continent,
            forest_origin=request.forest_origin,
            forest_status=request.forest_status,
        )

    def analyze(self, request: GeospatialAnalysisInput) -> dict:
        self.provider.window_expansion_months = request.window_expansion_months
        aoi = self.build_aoi(request)
        project = self.build_project(request, aoi)

        bundle = observe_all(
            self.provider,
            aoi,
            declared_land_use=request.land_use.value,
            current_year=request.current_year,
            baseline_year=request.baseline_year,
        )

        decision = select_biomass_source(
            biomass=bundle.biomass, consistency=bundle.consistency
        )
        use_remote_biomass = decision.selected is BiomassSourceLevel.GEDI_VALID_OBSERVATIONS

        inventory, adapter_warnings = self.adapter.to_inventory(
            bundle,
            project_id=project.project_id,
            inventory_id=f"gee-{request.current_year}-{aoi.geometry_hash[:8]}",
            year=request.current_year,
            biomass=bundle.biomass if use_remote_biomass else None,
        )

        baseline_inventory = None
        if request.baseline_year is not None:
            baseline_decision = select_biomass_source(
                biomass=bundle.baseline_biomass, consistency=bundle.consistency
            )
            if baseline_decision.selected is BiomassSourceLevel.GEDI_VALID_OBSERVATIONS:
                baseline_inventory, baseline_warnings = self.adapter.to_inventory(
                    bundle,
                    project_id=project.project_id,
                    inventory_id=f"gee-{request.baseline_year}-{aoi.geometry_hash[:8]}",
                    year=request.baseline_year,
                    biomass=bundle.baseline_biomass,
                )
                adapter_warnings.extend(baseline_warnings)
            else:
                adapter_warnings.append(
                    f"Baseline {request.baseline_year} sem biomassa comparável: "
                    f"{baseline_decision.reason}"
                )

        engine = CarbonEngine(
            self.registry,
            CarbonEngineConfig(strict_factor_validation=request.strict_factor_validation),
        )
        result = engine.calculate(
            project, inventory, baseline_inventory=baseline_inventory
        )

        support = compute_remote_sensing_support(bundle, decision)
        warnings = list(dict.fromkeys([*bundle.warnings, *adapter_warnings]))

        return {
            "result_type": RESULT_TYPE,
            "input": request.model_dump(mode="json"),
            "geometry": {
                "geometry_source": aoi.geometry_source.value,
                "geometry_area_ha": aoi.area_ha,
                "area_source": aoi.area_source.value,
                "declared_area_ha": aoi.declared_area_ha,
                "buffer_radius_m": aoi.buffer_radius_m,
                "geometry_hash": aoi.geometry_hash,
                "centroid": {"lat": aoi.lat, "lon": aoi.lon},
                "geojson": aoi.geojson,
                "notes": aoi.notes,
            },
            "remote_sensing": {
                "biomass": bundle.biomass.model_dump(mode="json"),
                "baseline_biomass": bundle.baseline_biomass.model_dump(mode="json")
                if bundle.baseline_biomass
                else None,
                "canopy": bundle.canopy.model_dump(mode="json"),
                "land_cover": bundle.land_cover.model_dump(mode="json"),
                "vegetation_indices": bundle.vegetation_indices.model_dump(mode="json"),
                "change": bundle.change.model_dump(mode="json"),
                "consistency": bundle.consistency.model_dump(mode="json"),
                "source_decision": decision.model_dump(mode="json"),
            },
            "carbon": result.model_dump(mode="json"),
            "quality": {
                "engine_confidence": result.quality.model_dump(mode="json")
                if result.quality
                else None,
                "remote_sensing_support": support,
                "note": (
                    "confidence_score (motor), data_quality_score (rastreabilidade), "
                    "remote_sensing_support (qualidade da observação) e uncertainty "
                    "(propagação estatística) são quatro coisas distintas e não se "
                    "substituem."
                ),
            },
            "provenance": {
                "engine_version": ENGINE_VERSION,
                "remote_sensing_layer_version": REMOTE_SENSING_LAYER_VERSION,
                "datasets": dataset_catalog(),
                "observations": {
                    "biomass": bundle.biomass.provenance.model_dump(mode="json")
                    if bundle.biomass.provenance
                    else None,
                    "canopy": bundle.canopy.provenance.model_dump(mode="json")
                    if bundle.canopy.provenance
                    else None,
                    "land_cover": bundle.land_cover.provenance.model_dump(mode="json")
                    if bundle.land_cover.provenance
                    else None,
                    "vegetation_indices": bundle.vegetation_indices.provenance.model_dump(
                        mode="json"
                    )
                    if bundle.vegetation_indices.provenance
                    else None,
                },
                "cache": self.provider.cache.stats(),
                "audit": result.audit.model_dump(mode="json") if result.audit else None,
            },
            "warnings": warnings,
            "disclaimer": DISCLAIMER,
        }


def compute_remote_sensing_support(
    bundle: RemoteSensingBundle, decision=None
) -> dict:
    """Indicador de qualidade da OBSERVAÇÃO remota (0-100), com drivers."""
    drivers: list[str] = []
    penalties: list[str] = []
    biomass = bundle.biomass

    support_component = SUPPORT_SCORE.get(biomass.support, 0.0)
    if biomass.support is SamplingSupport.USABLE:
        drivers.append(f"Suporte amostral utilizável: {biomass.sample_count} footprints.")
    else:
        penalties.append(f"Suporte amostral '{biomass.support.value}'.")

    fraction = biomass.sampled_fraction_of_aoi or 0.0
    fraction_component = min(fraction / SAMPLED_FRACTION_SATURATION, 1.0)
    if fraction > 0:
        drivers.append(f"Fração da AOI amostrada por footprints: {fraction * 100:.3f}%.")

    if biomass.uncertainty_available:
        uncertainty_component = 1.0
        drivers.append("Incerteza amostral calculada a partir da dispersão observada.")
    else:
        uncertainty_component = 0.0
        penalties.append("Incerteza amostral não calculável — nenhum valor foi arbitrado.")

    window = biomass.window
    temporal_component = 0.0
    if window is not None and window.actual_observation_start:
        observed_year = int(str(window.actual_observation_start)[:4])
        temporal_component = (
            1.0 if observed_year == window.requested_year else TEMPORAL_MISMATCH_SCORE
        )
        if temporal_component < 1.0:
            penalties.append(
                f"Observação efetiva em {observed_year}, diferente do ano solicitado "
                f"{window.requested_year}."
            )
    else:
        penalties.append("Janela de observação efetiva não determinada.")

    indices = bundle.vegetation_indices
    if indices.available and indices.cloud_masked_fraction is not None:
        cloud_component = max(1.0 - indices.cloud_masked_fraction, 0.0)
        if indices.cloud_masked_fraction > 0:
            drivers.append(
                f"Fração da AOI mascarada por nuvem no composto: "
                f"{indices.cloud_masked_fraction * 100:.1f}%."
            )
    else:
        cloud_component = 0.0
        penalties.append("Condições de nuvem não avaliadas (sem composto Sentinel-2).")

    consistency = bundle.consistency
    if consistency.blocking:
        consistency_component = 0.0
        penalties.append(consistency.message or "Incoerência bloqueante de cobertura.")
    elif consistency.consistent:
        consistency_component = 1.0
        drivers.append("Cobertura observada compatível com o uso da terra declarado.")
    elif consistency.checked:
        consistency_component = 0.5
        penalties.append(consistency.message or "Cobertura observada atípica para o uso declarado.")
    else:
        consistency_component = 0.0
        penalties.append("Consistência de cobertura não verificada.")

    weights = REMOTE_SENSING_CONFIDENCE_WEIGHTS
    raw = (
        support_component * weights["sampling_support"]
        + fraction_component * weights["sampled_fraction_of_aoi"]
        + uncertainty_component * weights["uncertainty_declared"]
        + temporal_component * weights["temporal_proximity"]
        + cloud_component * weights["cloud_conditions"]
        + consistency_component * weights["land_cover_consistency"]
    )
    score = int(round(raw))

    if biomass.support is not SamplingSupport.USABLE and score > NON_USABLE_SUPPORT_CAP:
        penalties.append(
            f"Score limitado a {NON_USABLE_SUPPORT_CAP} por suporte amostral "
            f"insuficiente (era {score})."
        )
        score = NON_USABLE_SUPPORT_CAP
    if consistency.blocking:
        penalties.append(f"Score zerado por incoerência bloqueante (era {score}).")
        score = 0

    return {
        "remote_sensing_support_score": score,
        "weights": weights,
        "drivers": drivers,
        "penalties": penalties,
        "biomass_source_selected": decision.selected.value if decision else None,
        "biomass_source_reason": decision.reason if decision else None,
        "biomass_sources_rejected": decision.rejected if decision else [],
        "disclaimer": (
            "Indicador interno GEØ.IA da qualidade da OBSERVAÇÃO geoespacial. "
            "Não é probabilidade, não é certificação e não substitui a análise "
            "de incerteza. Origem em satélite não aumenta a confiança por si só."
        ),
    }
