"""
Manejo y clasificación de errores del sistema.
Define las tres clases de error y el mecanismo de reintentos con backoff.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable


class ClaseError(str, Enum):
    """Clasificación de errores según su naturaleza y tratamiento."""

    TRANSITORIO = "transitorio"  # timeout, conexión, 429/5xx → reintentar
    DATOS = "datos"              # contrato inválido, producto inexistente → no reintentar
    SISTEMA = "sistema"          # credenciales, configuración → detener y alertar


@dataclass
class ErrorProceso:
    """Registro de un error ocurrido durante el proceso."""

    nodo: str
    clase_error: ClaseError
    mensaje: str
    carga_original: dict = field(default_factory=dict)
    momento: str = field(default_factory=lambda: _timestamp_ahora())
    identificador: str = field(default_factory=lambda: str(uuid.uuid4()))


def _timestamp_ahora() -> str:
    """Devuelve la marca de tiempo actual en formato ISO 8601."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def clasificar_error(exc: Exception) -> ClaseError:
    """
    Clasifica una excepción en una de las tres clases de error.

    - ConnectionError, TimeoutError → TRANSITORIO
    - ValueError, KeyError, FileNotFoundError → DATOS
    - Cualquier otro → SISTEMA
    """
    if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
        return ClaseError.TRANSITORIO
    if isinstance(exc, (ValueError, KeyError, FileNotFoundError, json.JSONDecodeError)):
        return ClaseError.DATOS
    return ClaseError.SISTEMA


def registrar_error(error: ErrorProceso, archivo: str) -> None:
    """Agrega el error a la cola de errores (archivo JSON)."""
    ruta = Path(archivo)
    ruta.parent.mkdir(parents=True, exist_ok=True)

    contenido = ruta.read_text(encoding="utf-8").strip() if ruta.exists() else ""
    cola: list[dict] = json.loads(contenido) if contenido else []

    cola.append({
        "momento": error.momento,
        "identificador": error.identificador,
        "nodo": error.nodo,
        "clase_error": error.clase_error.value,
        "mensaje": error.mensaje,
        "carga_original": error.carga_original,
    })

    ruta.write_text(json.dumps(cola, ensure_ascii=False, indent=2), encoding="utf-8")


def ejecutar_con_reintentos(
    fn: Callable,
    *args: Any,
    max_intentos: int = 3,
    espera_base: float = 1.0,
    **kwargs: Any,
) -> Any:
    """
    Ejecuta una función con reintentos para errores transitorios.
    Backoff exponencial: 1 s, 2 s, 4 s (configurable con espera_base).

    Si el error no es transitorio, lo propaga inmediatamente.
    Si se agotan los intentos, propaga la última excepción.
    """
    ultimo_error: Exception | None = None

    for intento in range(max_intentos):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            clase = clasificar_error(exc)
            if clase != ClaseError.TRANSITORIO:
                raise
            ultimo_error = exc
            if intento < max_intentos - 1:
                tiempo_espera = espera_base * (2 ** intento)
                time.sleep(tiempo_espera)

    raise ultimo_error  # type: ignore[misc]
