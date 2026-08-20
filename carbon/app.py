"""App FastAPI standalone — apenas para desenvolvimento/demonstração.

No backend GEØ.IA, NÃO usar este arquivo: incluir o router no app existente.

    from carbon.api.routes import router as carbon_router
    app.include_router(carbon_router)
"""

from __future__ import annotations

from fastapi import FastAPI

from .api.routes import router
from .version import ENGINE_VERSION

app = FastAPI(title="GEØ.IA Carbon", version=ENGINE_VERSION)
app.include_router(router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "engine_version": ENGINE_VERSION}
