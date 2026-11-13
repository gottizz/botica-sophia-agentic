"""
Herramienta LangChain para consultar el inventario de productos.
Busca por id_producto Y sede para manejar el caso de productos en múltiples sedes.
"""
from __future__ import annotations

import json
from pathlib import Path

from langchain_core.tools import tool

# Ruta del JSON de inventario relativa a la raíz del proyecto
_RUTA_INVENTARIO = Path(__file__).parent.parent.parent / "conocimiento" / "datos" / "inventario.json"


@tool
def consultar_inventario(id_producto: int, sede: str) -> dict:
    """
    Consulta el inventario para un producto y sede específicos.

    Args:
        id_producto: Identificador numérico del producto.
        sede: Nombre exacto de la sede (p. ej. "Sede Bolognesi 606").

    Returns:
        dict con los datos del inventario, o dict con clave 'error' si no se encuentra.
    """
    try:
        contenido = _RUTA_INVENTARIO.read_text(encoding="utf-8")
        inventario: list[dict] = json.loads(contenido)
    except FileNotFoundError:
        return {"error": f"Archivo de inventario no encontrado: {_RUTA_INVENTARIO}"}
    except json.JSONDecodeError as exc:
        return {"error": f"Error al leer inventario JSON: {exc}"}

    sede_norm = sede.strip().lower()
    for registro in inventario:
        if (
            registro.get("id_producto") == id_producto
            and registro.get("sede", "").strip().lower() == sede_norm
        ):
            return registro

    return {
        "error": (
            f"Producto id={id_producto} no encontrado en sede '{sede}'. "
            "Verifique el id_producto y la sede."
        )
    }
