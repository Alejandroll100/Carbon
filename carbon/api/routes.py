"""Rotas HTTP do módulo Carbon.

PONTO DE INTEGRAÇÃO: este arquivo expõe um ``APIRouter``. No backend GEØ.IA,
incluir com ``app.include_router(carbon_router)`` e substituir as dependências
``get_repository`` / ``get_engine`` pelas do container existente (sessão de
banco, auth, logging). Nenhuma infraestrutura nova é criada aqui.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from ..config.gee import (
    EarthEngineAuthenticationError,
    EarthEngineDisabledError,
    EarthEngineNotInstalledError,
    GEEConfig,
)
from ..factors.allometric_equations import list_equations
from ..factors.registry import FactorRegistry
from ..core.carbon_engine import METHODOLOGY_FRAMEWORK, CarbonEngine, CarbonEngineConfig
from ..services.gee_cache import GEEQueryCache
from ..services.gee_client import GEEQueryError, RealEarthEngineClient
from ..services.gee_datasets import dataset_catalog
from ..services.gee_provider import GoogleEarthEngineCarbonProvider
from ..services.geometry_service import GeometryError
from ..services.geospatial_analysis import GeospatialCarbonService
from ..models.inventory import CarbonInventory, Plot
from ..models.project import CarbonProject
from ..models.result import DISCLAIMER, CarbonResult
from ..services.project_repository import (
    CarbonRepository,
    DuplicateInventoryError,
    InMemoryCarbonRepository,
    ProjectNotFoundError,
)
from ..utils.validation import PhysicalValidationError
from ..version import ENGINE_VERSION, METHODOLOGY_VERSION
from .schemas import (
    CalculateRequest,
    CreateInventoryRequest,
    CreateProjectRequest,
    EmissionRequest,
    EventRequest,
    GeospatialAnalyzeRequest,
    SoilMeasurementRequest,
    TreeMeasurementRequest,
)

router = APIRouter(prefix="/api/carbon", tags=["carbon"])

_repository = InMemoryCarbonRepository()
_registry = FactorRegistry.load_default()


def get_repository() -> CarbonRepository:
    """Substituir pela dependência de banco do backend existente."""
    return _repository


def get_registry() -> FactorRegistry:
    return _registry


RepositoryDep = Annotated[CarbonRepository, Depends(get_repository)]
RegistryDep = Annotated[FactorRegistry, Depends(get_registry)]


# --- projetos ---------------------------------------------------------------

@router.post("/projects", status_code=status.HTTP_201_CREATED, response_model=CarbonProject)
def create_project(payload: CreateProjectRequest, repo: RepositoryDep) -> CarbonProject:
    project = CarbonProject(
        project_id=payload.project_id or f"geoia-carbon-{uuid.uuid4().hex[:8]}",
        **payload.model_dump(exclude={"project_id"}),
    )
    return repo.save_project(project)


@router.get("/projects/{project_id}", response_model=CarbonProject)
def get_project(project_id: str, repo: RepositoryDep) -> CarbonProject:
    try:
        return repo.get_project(project_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


# --- inventários ------------------------------------------------------------

@router.post(
    "/projects/{project_id}/inventory",
    status_code=status.HTTP_201_CREATED,
    response_model=CarbonInventory,
)
def create_inventory(
    project_id: str, payload: CreateInventoryRequest, repo: RepositoryDep
) -> CarbonInventory:
    try:
        repo.get_project(project_id)
        inventory = CarbonInventory(
            inventory_id=payload.inventory_id or f"inv-{uuid.uuid4().hex[:8]}",
            project_id=project_id,
            **payload.model_dump(exclude={"inventory_id"}),
        )
        return repo.save_inventory(inventory)
    except ProjectNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except DuplicateInventoryError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except PhysicalValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


@router.get("/projects/{project_id}/inventories", response_model=list[CarbonInventory])
def list_inventories(project_id: str, repo: RepositoryDep) -> list[CarbonInventory]:
    try:
        return repo.list_inventories(project_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.post(
    "/projects/{project_id}/soil",
    status_code=status.HTTP_201_CREATED,
    response_model=CarbonInventory,
)
def add_soil_measurement(
    project_id: str, payload: SoilMeasurementRequest, repo: RepositoryDep
) -> CarbonInventory:
    """Cria nova REVISÃO do inventário com a medição de solo anexada."""
    try:
        return repo.amend_inventory(
            project_id, payload.inventory_id, {"soil": payload.soil}
        )
    except ProjectNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.post(
    "/projects/{project_id}/trees",
    status_code=status.HTTP_201_CREATED,
    response_model=CarbonInventory,
)
def add_tree_measurements(
    project_id: str, payload: TreeMeasurementRequest, repo: RepositoryDep
) -> CarbonInventory:
    """Cria nova REVISÃO do inventário com parcelas/árvores anexadas."""
    plots = list(payload.plots)
    if payload.trees:
        if not payload.plot_area_m2:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "plot_area_m2 é obrigatório quando 'trees' é enviado sem estrutura de parcela: "
                "sem área amostrada não há como expandir para o projeto.",
            )
        plots.append(
            Plot(
                plot_id=payload.plot_id or f"plot-{uuid.uuid4().hex[:6]}",
                area_m2=payload.plot_area_m2,
                trees=payload.trees,
            )
        )
    try:
        current = repo.latest_revision(project_id, payload.inventory_id)  # type: ignore[attr-defined]
        return repo.amend_inventory(
            project_id, payload.inventory_id, {"plots": list(current.plots) + plots}
        )
    except ProjectNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


# --- cálculo ----------------------------------------------------------------

@router.post("/projects/{project_id}/calculate", response_model=CarbonResult)
def calculate(
    project_id: str,
    payload: CalculateRequest,
    repo: RepositoryDep,
    registry: RegistryDep,
) -> CarbonResult:
    try:
        project = repo.get_project(project_id)
        inventory = repo.latest_revision(project_id, payload.inventory_id)  # type: ignore[attr-defined]
        baseline = (
            repo.latest_revision(project_id, payload.baseline_inventory_id)  # type: ignore[attr-defined]
            if payload.baseline_inventory_id
            else None
        )
    except ProjectNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    events = list(payload.events)
    emissions = list(payload.operational_emissions)
    if payload.use_stored_events:
        events += list(repo.list_events(project_id))
        emissions += list(repo.list_emissions(project_id))

    engine = CarbonEngine(
        registry,
        CarbonEngineConfig(strict_factor_validation=payload.strict_factor_validation),
    )
    try:
        result = engine.calculate(
            project,
            inventory,
            baseline_inventory=baseline,
            events=events,
            operational_emissions=emissions,
            mode=payload.mode,
            project_parameters=payload.project_parameters,
        )
    except PhysicalValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return repo.save_result(result)


@router.get("/projects/{project_id}/results", response_model=CarbonResult)
def get_results(project_id: str, repo: RepositoryDep) -> CarbonResult:
    try:
        repo.get_project(project_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    result = repo.latest_result(project_id)
    if result is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Nenhum cálculo registrado para este projeto. Execute POST /calculate.",
        )
    return result


@router.get("/projects/{project_id}/balance")
def get_balance(project_id: str, repo: RepositoryDep) -> dict:
    result = get_results(project_id, repo)
    return {
        "project_id": project_id,
        "land_carbon": {
            "stock": result.carbon_stock.model_dump() if result.carbon_stock else None,
            "change": result.change.model_dump() if result.change else None,
            "removal": result.removal.model_dump() if result.removal else None,
            "losses": result.losses.model_dump() if result.losses else None,
        },
        "operational_emissions": result.operational_emissions.model_dump()
        if result.operational_emissions
        else None,
        "net_carbon_balance": result.net_balance.model_dump() if result.net_balance else None,
        "disclaimer": DISCLAIMER,
    }


# --- eventos e emissões operacionais ----------------------------------------

@router.post("/projects/{project_id}/events", status_code=status.HTTP_201_CREATED)
def add_event(project_id: str, payload: EventRequest, repo: RepositoryDep) -> dict:
    try:
        event = repo.save_event(project_id, payload.event)
    except ProjectNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return {
        "registered": True,
        "event": event.model_dump(mode="json"),
        "note": "Evento registrado. Perda de carbono só entra no balanço se quantificada "
        "(carbon_loss_tC). O motor não estima perda a partir do tipo de evento.",
    }


@router.post("/projects/{project_id}/operational-emissions", status_code=status.HTTP_201_CREATED)
def add_operational_emission(
    project_id: str, payload: EmissionRequest, repo: RepositoryDep
) -> dict:
    try:
        entry = repo.save_emission(project_id, payload.entry)
    except ProjectNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return {
        "registered": True,
        "entry": entry.model_dump(mode="json"),
        "note": "Emissão operacional é contabilizada separadamente do estoque biogênico.",
    }


# --- camada geoespacial (Google Earth Engine) -------------------------------
#
# Endpoints ADICIONAIS. Nenhuma das 13 rotas anteriores muda de assinatura ou
# de comportamento.

_geospatial_service: CarbonRepository | None = None  # type: ignore[assignment]


def get_geospatial_service() -> GeospatialCarbonService:
    """Serviço geoespacial. Sobrescrever nos testes com dependency_overrides."""
    global _geospatial_service
    if _geospatial_service is None:
        config = GEEConfig.from_env()
        try:
            client = RealEarthEngineClient(config)
        except EarthEngineDisabledError as exc:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
        except EarthEngineNotInstalledError as exc:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
        except EarthEngineAuthenticationError as exc:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
        _geospatial_service = GeospatialCarbonService(  # type: ignore[assignment]
            GoogleEarthEngineCarbonProvider(
                client, cache=GEEQueryCache(ttl_seconds=config.cache_ttl_seconds)
            ),
            registry=get_registry(),
        )
    return _geospatial_service  # type: ignore[return-value]


GeospatialDep = Annotated[GeospatialCarbonService, Depends(get_geospatial_service)]


@router.post("/geospatial/analyze")
def geospatial_analyze(
    payload: GeospatialAnalyzeRequest, service: GeospatialDep
) -> dict:
    """Analisa uma AOI (lat/lon + área, ou polígono GeoJSON) via Earth Engine.

    A resposta separa observação remota, resultado de carbono, qualidade e
    proveniência. Nenhuma indisponibilidade vira zero.
    """
    try:
        return service.analyze(payload)
    except (GeometryError, PhysicalValidationError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    except EarthEngineAuthenticationError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    except GEEQueryError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc


@router.post("/geospatial/calculate")
def geospatial_calculate(
    payload: GeospatialAnalyzeRequest, service: GeospatialDep
) -> dict:
    """Alias de ``/geospatial/analyze`` — mesma entrada, mesma saída."""
    return geospatial_analyze(payload, service)


@router.get("/geospatial/datasets")
def geospatial_datasets() -> dict:
    """Catálogo declarado dos produtos geoespaciais e o modo de autenticação."""
    config = GEEConfig.from_env()
    return {
        "provider": "google_earth_engine",
        "configuration": config.public_summary(),
        "datasets": dataset_catalog(),
        "scientific_rules": [
            "Índice espectral (NDVI/EVI/NBR/NDMI) nunca é convertido em carbono.",
            "GEDI entrega biomassa aérea seca; a fração de carbono é aplicada "
            "uma única vez, pelo Carbon Engine.",
            "Ausência de observação é declarada, nunca convertida em zero.",
            "Incerteza reportada cobre apenas a componente amostral; o erro do "
            "modelo GEDI é preservado em bruto e declarado como não incluído.",
        ],
        "disclaimer": DISCLAIMER,
    }


# --- metadados --------------------------------------------------------------

@router.get("/factors")
def list_factors(registry: RegistryDep, category: str | None = None) -> dict:
    factors = registry.all()
    if category:
        factors = [f for f in factors if f.category == category]
    return {
        "factor_database_version": registry.version,
        "reference_database_version": registry.references.version,
        "count": len(factors),
        "validated": [f.factor_id for f in factors if f.validation_status.value == "validated"],
        "pending_validation": [f.factor_id for f in factors if f.requires_validation],
        "validated_absence": [f.factor_id for f in factors if f.is_validated_absence],
        "without_value": [f.factor_id for f in factors if not f.has_value],
        "factors": [f.model_dump(mode="json") for f in factors],
        "references": [r.model_dump() for r in registry.references.all()],
    }


@router.get("/methodologies")
def list_methodologies(registry: RegistryDep) -> dict:
    equations = list_equations()
    return {
        "engine_version": ENGINE_VERSION,
        "methodology_version": METHODOLOGY_VERSION,
        "factor_database_version": registry.version,
        "framework": METHODOLOGY_FRAMEWORK,
        "implemented_scope": [
            "Carbon Inventory",
            "Carbon Stock Estimate",
            "Carbon Removal Estimate",
        ],
        "not_implemented": ["Carbon Credit Potential", "Verified Carbon Credits"],
        "tiers_supported": {"tier_1": True, "tier_2": "arquitetura pronta", "tier_3": "arquitetura pronta"},
        "allometric_equations": [e.model_dump() for e in equations],
        "disclaimer": DISCLAIMER,
    }
