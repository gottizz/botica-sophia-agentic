"""
Funciones de persistencia para solicitudes, alertas y cola de revisión.
No son @tool de LangChain; son funciones Python puras llamadas desde los nodos del grafo.
"""
from __future__ import annotations

import json
from pathlib import Path


def _leer_json(ruta: Path) -> list[dict]:
    """Lee un archivo JSON de lista. Crea el archivo con [] si no existe."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    if not ruta.exists():
        ruta.write_text("[]", encoding="utf-8")
        return []
    contenido = ruta.read_text(encoding="utf-8").strip()
    return json.loads(contenido) if contenido else []


def _escribir_json(ruta: Path, datos: list[dict]) -> None:
    """Escribe la lista de dicts en el archivo JSON."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")


def registrar_solicitud(solicitud: dict, archivo: str) -> None:
    """
    Agrega una solicitud al archivo JSON de solicitudes.
    La solicitud debe incluir la clave de idempotencia para verificaciones futuras.
    """
    ruta = Path(archivo)
    solicitudes = _leer_json(ruta)
    solicitudes.append(solicitud)
    _escribir_json(ruta, solicitudes)


def registrar_alerta(alerta: dict, archivo: str) -> None:
    """Agrega una alerta al archivo JSON de alertas."""
    ruta = Path(archivo)
    alertas = _leer_json(ruta)
    alertas.append(alerta)
    _escribir_json(ruta, alertas)


def encolar_revision(item: dict, archivo: str) -> None:
    """Encola un ítem para revisión humana en el archivo JSON correspondiente."""
    ruta = Path(archivo)
    cola = _leer_json(ruta)
    cola.append(item)
    _escribir_json(ruta, cola)
