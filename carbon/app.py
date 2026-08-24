"""App FastAPI standalone — apenas para desenvolvimento/demonstração."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router
from .version import ENGINE_VERSION

app = FastAPI(
    title="GEØ.IA Carbon",
    version=ENGINE_VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://geoiacarbon.goskip.app",
    ],
    allow_origin_regex=r"https://.*\.goskip\.app$",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "engine_version": ENGINE_VERSION,
    }
