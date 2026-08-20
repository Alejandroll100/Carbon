"""GEØ.IA Carbon — motor de inventário e estoque de carbono para florestas,
restauração e sistemas agroflorestais.

Escopo desta versão (P0):

    Carbon Inventory        ✔
    Carbon Stock Estimate   ✔
    Carbon Removal Estimate ✔
    Carbon Credit Potential ✘ (não implementado)
    Verified Carbon Credits ✘ (não implementado)
"""

from .version import ENGINE_VERSION, FACTOR_DATABASE_VERSION, METHODOLOGY_VERSION

__all__ = [
    "ENGINE_VERSION",
    "FACTOR_DATABASE_VERSION",
    "METHODOLOGY_VERSION",
    "CarbonEngine",
    "CarbonEngineConfig",
    "router",
]


def __getattr__(name: str):  # import preguiçoso: evita puxar FastAPI sem necessidade
    if name in ("CarbonEngine", "CarbonEngineConfig"):
        from .core.carbon_engine import CarbonEngine, CarbonEngineConfig

        return {"CarbonEngine": CarbonEngine, "CarbonEngineConfig": CarbonEngineConfig}[name]
    if name == "router":
        from .api.routes import router

        return router
    raise AttributeError(name)
