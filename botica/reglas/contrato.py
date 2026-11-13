"""
Validación del contrato de entrada (reglas deterministas, sin LLM).
Los 8 campos deben cumplir las restricciones definidas en CLAUDE.md.
"""
from __future__ import annotations

import re
from typing import Any


def validar_contrato(datos: dict[str, Any]) -> tuple[bool, list[str]]:
    """
    Valida los 8 campos del contrato de entrada.

    Retorna:
        (True, [])          si todos los campos son válidos.
        (False, [errores])  si algún campo no cumple la regla.
    """
    errores: list[str] = []

    # id_producto: entero > 0
    id_producto = datos.get("id_producto")
    if not isinstance(id_producto, int) or isinstance(id_producto, bool) or id_producto <= 0:
        errores.append("id_producto debe ser un entero mayor que 0")

    # nombre_producto: texto 1-100 caracteres
    nombre = datos.get("nombre_producto", "")
    if not isinstance(nombre, str) or not (1 <= len(nombre.strip()) <= 100):
        errores.append("nombre_producto debe ser texto de 1 a 100 caracteres")

    # cantidad_disponible: entero >= 0
    cantidad_disp = datos.get("cantidad_disponible")
    if not isinstance(cantidad_disp, int) or isinstance(cantidad_disp, bool) or cantidad_disp < 0:
        errores.append("cantidad_disponible debe ser un entero mayor o igual a 0")

    # stock_minimo: entero >= 1
    stock_min = datos.get("stock_minimo")
    if not isinstance(stock_min, int) or isinstance(stock_min, bool) or stock_min < 1:
        errores.append("stock_minimo debe ser un entero mayor o igual a 1")

    # cantidad_solicitada: si está presente, entero > 0
    cantidad_sol = datos.get("cantidad_solicitada")
    if cantidad_sol is not None:
        if not isinstance(cantidad_sol, int) or isinstance(cantidad_sol, bool) or cantidad_sol <= 0:
            errores.append("cantidad_solicitada, si está presente, debe ser un entero mayor que 0")

    # sede: texto no vacío
    sede = datos.get("sede", "")
    if not isinstance(sede, str) or not sede.strip():
        errores.append("sede debe ser texto no vacío")

    # fecha_solicitud: formato AAAA-MM-DD
    fecha = datos.get("fecha_solicitud", "")
    patron_fecha = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    if not isinstance(fecha, str) or not patron_fecha.match(fecha):
        errores.append("fecha_solicitud debe tener el formato AAAA-MM-DD")

    # responsable: texto 1-120 caracteres
    responsable = datos.get("responsable", "")
    if not isinstance(responsable, str) or not (1 <= len(responsable.strip()) <= 120):
        errores.append("responsable debe ser texto de 1 a 120 caracteres")

    valido = len(errores) == 0
    return valido, errores
