"""
Módulo de trazabilidad: registra la traza de cada nodo del grafo.
Cada ejecución de nodo appends su traza al archivo JSON de trazas.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def registrar_traza(
    nodo: str,
    entrada: dict,
    salida: dict,
    duracion_ms: float,
    archivo: str,
) -> None:
    """
    Registra la traza de ejecución de un nodo del grafo en el archivo JSON.

    Args:
        nodo: Nombre del nodo que se ejecutó.
        entrada: Resumen de los datos de entrada al nodo.
        salida: Resumen de los datos de salida del nodo.
        duracion_ms: Duración de la ejecución en milisegundos.
        archivo: Ruta al archivo JSON donde se guardan las trazas.
    """
    ruta = Path(archivo)
    ruta.parent.mkdir(parents=True, exist_ok=True)

    contenido = ruta.read_text(encoding="utf-8").strip() if ruta.exists() else ""
    trazas: list[dict] = json.loads(contenido) if contenido else []

    trazas.append({
        "momento": datetime.now(timezone.utc).isoformat(),
        "nodo": nodo,
        "duracion_ms": round(duracion_ms, 2),
        "entrada": entrada,
        "salida": salida,
    })

    ruta.write_text(json.dumps(trazas, ensure_ascii=False, indent=2), encoding="utf-8")
