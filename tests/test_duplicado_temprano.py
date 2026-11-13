"""
Pruebas del nodo_detectar_duplicado: verificación temprana de idempotencia, sin LLM.
"""
from __future__ import annotations

import json

from botica.orquestador.grafo import nodo_detectar_duplicado
from botica.reglas.idempotencia import calcular_clave


def _estado(**cambios) -> dict:
    base = {
        "id_producto": 25, "nombre_producto": "Paracetamol 500 mg", "cantidad_disponible": 8,
        "stock_minimo": 15, "cantidad_solicitada": None, "sede": "Sede Bolognesi 606",
        "fecha_solicitud": "2026-01-15", "responsable": "Juana Pérez",
    }
    base.update(cambios)
    return base


def _registrar(rutas: dict, cantidad: int) -> str:
    """Escribe en el archivo temporal una solicitud ya registrada para Paracetamol."""
    clave = calcular_clave(25, "Sede Bolognesi 606", cantidad, "2026-01-15", 8)
    rutas["solicitudes"].write_text(json.dumps([{
        "codigo_solicitud": "SOL-20260115-" + clave[:6].upper(), "clave_idempotencia": clave,
        "prioridad": "alta", "cantidad_solicitada": cantidad, "estado_solicitud": "PENDIENTE_COTIZACION",
    }]), encoding="utf-8")
    return clave


def test_detecta_duplicado_con_cantidad_sugerida(inventario_limpio):
    """Sin cantidad indicada se usa la sugerida (15*2-8 = 22): misma clave → YA_PROCESADA."""
    clave = _registrar(inventario_limpio, 22)
    r = nodo_detectar_duplicado(_estado())
    assert r["ya_procesada"] is True
    assert r["clave_idempotencia"] == clave
    assert r["solicitud_registrada"]["cantidad_solicitada"] == 22


def test_otra_cantidad_no_es_duplicado(inventario_limpio):
    _registrar(inventario_limpio, 22)
    r = nodo_detectar_duplicado(_estado(cantidad_solicitada=30))
    assert r["ya_procesada"] is False


def test_datos_contradictorios_siguen_a_a01(inventario_limpio):
    """Si el stock informado no coincide con el inventario, no se marca duplicado: A01 escala."""
    _registrar(inventario_limpio, 22)
    r = nodo_detectar_duplicado(_estado(cantidad_disponible=5))
    assert r["ya_procesada"] is False
    assert "contradictorios" in r["trazas"][0]["motivo"]


def test_producto_inexistente_sigue_a_a01(inventario_limpio):
    r = nodo_detectar_duplicado(_estado(id_producto=9999))
    assert r["ya_procesada"] is False
    assert "no encontrado" in r["trazas"][0]["motivo"]


def test_sin_reposicion_no_busca_duplicado(inventario_limpio):
    r = nodo_detectar_duplicado(_estado(id_producto=28, nombre_producto="Ibuprofeno 400 mg",
                                        cantidad_disponible=40, stock_minimo=15))
    assert r["ya_procesada"] is False
    assert r["trazas"][0]["motivo"] == "no requiere reposición"
