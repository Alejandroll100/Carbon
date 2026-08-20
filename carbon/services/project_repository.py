"""Repositório de projetos e inventários.

PONTO DE INTEGRAÇÃO: o backend GEØ.IA já possui camada de banco. Implementar
``CarbonRepository`` sobre ela (SQLAlchemy/ORM existente) e injetar via
``get_repository`` na API. A implementação em memória abaixo existe para
testes e para o MVP rodar isolado.

Regra: inventários NUNCA são sobrescritos. ``save_inventory`` recusa
``inventory_id`` repetido — a série temporal precisa permanecer comparável.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

from ..models.inventory import CarbonInventory, OperationalEmissionEntry
from ..models.land import LandEvent
from ..models.project import CarbonProject
from ..models.result import CarbonResult


class DuplicateInventoryError(ValueError):
    pass


class ProjectNotFoundError(LookupError):
    pass


class CarbonRepository(Protocol):
    def save_project(self, project: CarbonProject) -> CarbonProject: ...
    def get_project(self, project_id: str) -> CarbonProject: ...
    def list_projects(self) -> list[CarbonProject]: ...
    def save_inventory(self, inventory: CarbonInventory) -> CarbonInventory: ...
    def list_inventories(self, project_id: str) -> list[CarbonInventory]: ...
    def get_inventory(self, project_id: str, inventory_id: str) -> CarbonInventory: ...
    def amend_inventory(self, project_id: str, base_id: str, patch: dict) -> CarbonInventory: ...
    def save_event(self, project_id: str, event: LandEvent) -> LandEvent: ...
    def list_events(self, project_id: str) -> list[LandEvent]: ...
    def save_emission(self, project_id: str, entry: OperationalEmissionEntry) -> OperationalEmissionEntry: ...
    def list_emissions(self, project_id: str) -> list[OperationalEmissionEntry]: ...
    def save_result(self, result: CarbonResult) -> CarbonResult: ...
    def latest_result(self, project_id: str) -> CarbonResult | None: ...


class InMemoryCarbonRepository:
    def __init__(self) -> None:
        self._projects: dict[str, CarbonProject] = {}
        self._inventories: dict[str, list[CarbonInventory]] = {}
        self._events: dict[str, list[LandEvent]] = {}
        self._emissions: dict[str, list[OperationalEmissionEntry]] = {}
        self._results: dict[str, list[CarbonResult]] = {}

    def save_project(self, project: CarbonProject) -> CarbonProject:
        self._projects[project.project_id] = project
        self._inventories.setdefault(project.project_id, [])
        return project

    def get_project(self, project_id: str) -> CarbonProject:
        try:
            return self._projects[project_id]
        except KeyError as exc:
            raise ProjectNotFoundError(f"Projeto não encontrado: {project_id}") from exc

    def list_projects(self) -> list[CarbonProject]:
        return list(self._projects.values())

    def save_inventory(self, inventory: CarbonInventory) -> CarbonInventory:
        self.get_project(inventory.project_id)
        existing = self._inventories.setdefault(inventory.project_id, [])
        if any(i.inventory_id == inventory.inventory_id for i in existing):
            raise DuplicateInventoryError(
                f"inventory_id já existe: {inventory.inventory_id}. Inventários são "
                "imutáveis — crie um novo id para registrar nova medição."
            )
        existing.append(inventory)
        return inventory

    def list_inventories(self, project_id: str) -> list[CarbonInventory]:
        self.get_project(project_id)
        return sorted(self._inventories.get(project_id, []), key=lambda i: (i.year, i.revision))

    def get_inventory(self, project_id: str, inventory_id: str) -> CarbonInventory:
        for inv in self._inventories.get(project_id, []):
            if inv.inventory_id == inventory_id:
                return inv
        raise ProjectNotFoundError(
            f"Inventário não encontrado: {inventory_id} (projeto {project_id})"
        )

    def latest_revision(self, project_id: str, base_id: str) -> CarbonInventory:
        """Última revisão de uma linhagem de inventário."""
        lineage = [
            inv
            for inv in self._inventories.get(project_id, [])
            if inv.inventory_id == base_id or inv.inventory_id.startswith(f"{base_id}::v")
        ]
        if not lineage:
            raise ProjectNotFoundError(f"Inventário não encontrado: {base_id}")
        return max(lineage, key=lambda i: i.revision)

    def amend_inventory(
        self, project_id: str, base_id: str, patch: dict
    ) -> CarbonInventory:
        """Cria NOVA revisão. O inventário anterior permanece intacto no histórico."""
        current = self.latest_revision(project_id, base_id)
        data = current.model_dump()
        data.update(patch)
        root = base_id.split("::v")[0]
        data["revision"] = current.revision + 1
        data["inventory_id"] = f"{root}::v{data['revision']}"
        data["supersedes"] = current.inventory_id
        data["created_at"] = datetime.now(timezone.utc)
        new_inv = CarbonInventory(**data)
        self._inventories.setdefault(project_id, []).append(new_inv)
        return new_inv

    def save_event(self, project_id: str, event: LandEvent) -> LandEvent:
        self.get_project(project_id)
        self._events.setdefault(project_id, []).append(event)
        return event

    def list_events(self, project_id: str) -> list[LandEvent]:
        return self._events.get(project_id, [])

    def save_emission(
        self, project_id: str, entry: OperationalEmissionEntry
    ) -> OperationalEmissionEntry:
        self.get_project(project_id)
        self._emissions.setdefault(project_id, []).append(entry)
        return entry

    def list_emissions(self, project_id: str) -> list[OperationalEmissionEntry]:
        return self._emissions.get(project_id, [])

    def save_result(self, result: CarbonResult) -> CarbonResult:
        self._results.setdefault(result.project_id, []).append(result)
        return result

    def latest_result(self, project_id: str) -> CarbonResult | None:
        results = self._results.get(project_id, [])
        return results[-1] if results else None
