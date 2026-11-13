"""
Fixtures compartidas para todos los tests.
Define LLMFalso, datos_base, rutas_temporales e inventario_limpio.
Los tests NUNCA llaman al LLM real ni escriben en conocimiento/datos/.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
from langchain_core.runnables import RunnableLambda

# Las pruebas no envían trazas a LangSmith (sin red); override=False de dotenv respeta este valor
os.environ["LANGSMITH_TRACING"] = "false"


_ROLES = {"system": "system", "human": "user", "ai": "assistant"}


def _a_mensajes(entrada: Any) -> Any:
    """Convierte el ChatPromptValue de la plantilla LCEL a [{"role", "content"}] para inspeccionarlo."""
    if hasattr(entrada, "to_messages"):
        return [
            {"role": _ROLES.get(m.type, m.type), "content": m.content}
            for m in entrada.to_messages()
        ]
    return entrada


def _RunnableConOutput(valor: Any, llamadas: list) -> RunnableLambda:
    """Simula llm.with_structured_output(esquema): un Runnable LCEL que devuelve el valor fijo."""

    def _responder(entrada: Any) -> Any:
        llamadas.append(_a_mensajes(entrada))
        return valor

    return RunnableLambda(_responder)


class LLMFalso:
    """
    Reemplazo del LLM de Groq para los tests.
    Se configura con valores esperados por esquema; nunca hace llamadas de red.
    """

    def __init__(self) -> None:
        self._salidas: dict[type, Any] = {}
        self.llamadas: list = []  # mensajes recibidos en cada invoke, para inspeccionar prompts

    def configurar(self, esquema: type, valor: Any) -> None:
        """Pre-configura la respuesta para un esquema Pydantic dado."""
        self._salidas[esquema] = valor

    def with_structured_output(self, esquema: type, **kwargs: Any) -> _RunnableConOutput:
        """Retorna un runnable que devuelve el valor configurado para el esquema."""
        valor = self._salidas.get(esquema)
        if valor is None:
            raise ValueError(
                f"LLMFalso: no se configuró una salida para el esquema {esquema.__name__}"
            )
        return _RunnableConOutput(valor, self.llamadas)


@pytest.fixture
def llm_falso() -> LLMFalso:
    """Instancia del LLM falso para cada test."""
    return LLMFalso()


@pytest.fixture
def datos_base() -> dict:
    """Datos mínimos válidos del contrato de entrada (Paracetamol, stock bajo)."""
    return {
        "id_producto": 25,
        "nombre_producto": "Paracetamol 500 mg",
        "cantidad_disponible": 8,
        "stock_minimo": 15,
        "cantidad_solicitada": None,
        "sede": "Sede Bolognesi 606",
        "fecha_solicitud": "2026-01-15",
        "responsable": "Juana Pérez",
    }


# Constantes de ruta (módulo, atributo, archivo) que escriben en conocimiento/datos/
_RUTAS_PERSISTENCIA = [
    ("botica.agentes.a01_inventario", "_RUTA_ERRORES", "cola_errores"),
    ("botica.agentes.a01_inventario", "_RUTA_TRAZAS", "trazas"),
    ("botica.agentes.a02_abastecimiento", "_RUTA_ERRORES", "cola_errores"),
    ("botica.agentes.a03_validador", "_RUTA_ERRORES", "cola_errores"),
    ("botica.orquestador.grafo", "_RUTA_SOLICITUDES", "solicitudes"),
    ("botica.orquestador.grafo", "_RUTA_ALERTAS", "alertas"),
    ("botica.orquestador.grafo", "_RUTA_COLA_REVISION", "cola_revision"),
    ("botica.orquestador.grafo", "_RUTA_COLA_ERRORES", "cola_errores"),
    ("botica.api.rutas", "_RUTA_TRAZAS", "trazas"),
]


@pytest.fixture(autouse=True)
def rutas_temporales(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """
    Redirige TODAS las rutas de persistencia a archivos temporales vacíos.
    Es autouse: ningún test escribe en los archivos reales de conocimiento/datos/.
    """
    import importlib

    archivos = {
        "solicitudes": tmp_path / "solicitudes.json",
        "alertas": tmp_path / "alertas.json",
        "cola_revision": tmp_path / "cola_revision.json",
        "cola_errores": tmp_path / "cola_errores.json",
        "trazas": tmp_path / "trazas.json",
    }
    for ruta in archivos.values():
        ruta.write_text("[]", encoding="utf-8")

    for modulo, atributo, archivo in _RUTAS_PERSISTENCIA:
        monkeypatch.setattr(importlib.import_module(modulo), atributo, str(archivos[archivo]))
    return archivos


@pytest.fixture
def inventario_limpio(rutas_temporales: dict[str, Path]) -> dict[str, Path]:
    """Rutas de los archivos JSON temporales de persistencia (ver rutas_temporales)."""
    return rutas_temporales
