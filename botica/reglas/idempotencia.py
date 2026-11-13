"""
Idempotencia: clave SHA-256, código de solicitud y verificación de duplicados.
La clave se verifica dos veces: al inicio (nodo_detectar_duplicado, sin LLM) y justo antes de registrar.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Optional


def calcular_clave(
    id_producto: int,
    sede: str,
    cantidad_solicitada: int,
    fecha_solicitud: str,
    cantidad_disponible: int,
) -> str:
    """
    Calcula la clave SHA-256 de idempotencia.

    Normaliza la sede (minúsculas, sin espacios extremos) y concatena
    los campos con '|' antes de calcular el hash.
    """
    sede_norm = sede.strip().lower()
    cadena = f"{id_producto}|{sede_norm}|{cantidad_solicitada}|{fecha_solicitud}|{cantidad_disponible}"
    return hashlib.sha256(cadena.encode("utf-8")).hexdigest()


def generar_codigo(clave: str, fecha: str) -> str:
    """
    Genera el código de solicitud en formato SOL-AAAAMMDD-XXXXXX.

    - fecha: formato AAAA-MM-DD (los guiones se eliminan para el código)
    - XXXXXX: 6 primeros caracteres de la clave SHA-256 en mayúsculas
    """
    fecha_compacta = fecha.replace("-", "")
    sufijo = clave[:6].upper()
    return f"SOL-{fecha_compacta}-{sufijo}"


def verificar_idempotencia(
    clave: str, archivo_solicitudes: str
) -> tuple[bool, Optional[dict]]:
    """
    Verifica si la clave ya existe en el archivo de solicitudes.

    Retorna:
        (True, solicitud_existente)  si ya fue procesada.
        (False, None)               si es una solicitud nueva.
    """
    ruta = Path(archivo_solicitudes)
    if not ruta.exists():
        return False, None

    try:
        contenido = ruta.read_text(encoding="utf-8").strip()
        solicitudes: list[dict] = json.loads(contenido) if contenido else []
    except (json.JSONDecodeError, OSError):
        return False, None

    for solicitud in solicitudes:
        if solicitud.get("clave_idempotencia") == clave:
            return True, solicitud

    return False, None
