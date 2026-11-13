"""
Aplicación principal FastAPI.
Punto de entrada del servidor web de Botica Sophia Agentic.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from botica.api.rutas import enrutador

_PAGINA = Path(__file__).parent / "estatica" / "index.html"

aplicacion = FastAPI(
    title="Botica Sophia Agentic",
    description=(
        "Sistema multiagente de abastecimiento de productos farmacéuticos. "
        "Detecta stock bajo y genera solicitudes de reposición validadas."
    ),
    version="0.1.0",
)

aplicacion.include_router(enrutador, prefix="/api/v1")


@aplicacion.get("/", include_in_schema=False)
def pagina_principal() -> FileResponse:
    """Interfaz web de la demo."""
    return FileResponse(_PAGINA, media_type="text/html")
