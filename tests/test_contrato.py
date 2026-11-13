"""
Pruebas de la función validar_contrato.
Verifica que los 8 campos del contrato de entrada se validen correctamente.
"""
from __future__ import annotations

import pytest

from botica.reglas.contrato import validar_contrato


@pytest.fixture
def entrada_valida() -> dict:
    """Datos válidos de referencia para los tests de contrato."""
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


def test_contrato_valido_completo(entrada_valida: dict) -> None:
    """Todos los campos válidos → debe retornar (True, [])."""
    valido, errores = validar_contrato(entrada_valida)
    assert valido is True
    assert errores == []


def test_contrato_valido_con_cantidad_solicitada(entrada_valida: dict) -> None:
    """cantidad_solicitada presente y válida → debe ser aceptada."""
    entrada_valida["cantidad_solicitada"] = 10
    valido, errores = validar_contrato(entrada_valida)
    assert valido is True
    assert errores == []


def test_contrato_id_producto_cero(entrada_valida: dict) -> None:
    """id_producto = 0 → debe fallar (regla: > 0)."""
    entrada_valida["id_producto"] = 0
    valido, errores = validar_contrato(entrada_valida)
    assert valido is False
    assert any("id_producto" in e for e in errores)


def test_contrato_id_producto_negativo(entrada_valida: dict) -> None:
    """id_producto negativo → debe fallar."""
    entrada_valida["id_producto"] = -5
    valido, errores = validar_contrato(entrada_valida)
    assert valido is False
    assert any("id_producto" in e for e in errores)


def test_contrato_nombre_producto_vacio(entrada_valida: dict) -> None:
    """nombre_producto vacío → debe fallar (regla: 1-100 chars)."""
    entrada_valida["nombre_producto"] = ""
    valido, errores = validar_contrato(entrada_valida)
    assert valido is False
    assert any("nombre_producto" in e for e in errores)


def test_contrato_nombre_producto_solo_espacios(entrada_valida: dict) -> None:
    """nombre_producto de solo espacios → debe fallar."""
    entrada_valida["nombre_producto"] = "   "
    valido, errores = validar_contrato(entrada_valida)
    assert valido is False
    assert any("nombre_producto" in e for e in errores)


def test_contrato_cantidad_disponible_negativa(entrada_valida: dict) -> None:
    """cantidad_disponible negativa → debe fallar (regla: >= 0)."""
    entrada_valida["cantidad_disponible"] = -1
    valido, errores = validar_contrato(entrada_valida)
    assert valido is False
    assert any("cantidad_disponible" in e for e in errores)


def test_contrato_cantidad_disponible_cero_es_valida(entrada_valida: dict) -> None:
    """cantidad_disponible = 0 → debe ser válida (Amoxicilina sin stock)."""
    entrada_valida["cantidad_disponible"] = 0
    valido, errores = validar_contrato(entrada_valida)
    assert valido is True
    assert errores == []


def test_contrato_stock_minimo_cero(entrada_valida: dict) -> None:
    """stock_minimo = 0 → debe fallar (regla: >= 1)."""
    entrada_valida["stock_minimo"] = 0
    valido, errores = validar_contrato(entrada_valida)
    assert valido is False
    assert any("stock_minimo" in e for e in errores)


def test_contrato_stock_minimo_negativo(entrada_valida: dict) -> None:
    """stock_minimo negativo → debe fallar."""
    entrada_valida["stock_minimo"] = -10
    valido, errores = validar_contrato(entrada_valida)
    assert valido is False
    assert any("stock_minimo" in e for e in errores)


def test_contrato_fecha_mal_formada(entrada_valida: dict) -> None:
    """fecha_solicitud con formato incorrecto → debe fallar."""
    entrada_valida["fecha_solicitud"] = "15/01/2026"
    valido, errores = validar_contrato(entrada_valida)
    assert valido is False
    assert any("fecha_solicitud" in e for e in errores)


def test_contrato_fecha_sin_guiones(entrada_valida: dict) -> None:
    """fecha_solicitud sin guiones → debe fallar."""
    entrada_valida["fecha_solicitud"] = "20260115"
    valido, errores = validar_contrato(entrada_valida)
    assert valido is False
    assert any("fecha_solicitud" in e for e in errores)


def test_contrato_responsable_demasiado_largo(entrada_valida: dict) -> None:
    """responsable con más de 120 chars → debe fallar."""
    entrada_valida["responsable"] = "A" * 121
    valido, errores = validar_contrato(entrada_valida)
    assert valido is False
    assert any("responsable" in e for e in errores)


def test_contrato_responsable_exactamente_120_chars(entrada_valida: dict) -> None:
    """responsable con exactamente 120 chars → debe ser válido."""
    entrada_valida["responsable"] = "A" * 120
    valido, errores = validar_contrato(entrada_valida)
    assert valido is True
    assert errores == []


def test_contrato_cantidad_solicitada_cero(entrada_valida: dict) -> None:
    """cantidad_solicitada = 0 → debe fallar si está presente (regla: > 0)."""
    entrada_valida["cantidad_solicitada"] = 0
    valido, errores = validar_contrato(entrada_valida)
    assert valido is False
    assert any("cantidad_solicitada" in e for e in errores)


def test_contrato_cantidad_solicitada_negativa(entrada_valida: dict) -> None:
    """cantidad_solicitada negativa → debe fallar si está presente."""
    entrada_valida["cantidad_solicitada"] = -5
    valido, errores = validar_contrato(entrada_valida)
    assert valido is False
    assert any("cantidad_solicitada" in e for e in errores)


def test_contrato_sede_vacia(entrada_valida: dict) -> None:
    """sede vacía → debe fallar."""
    entrada_valida["sede"] = ""
    valido, errores = validar_contrato(entrada_valida)
    assert valido is False
    assert any("sede" in e for e in errores)


def test_contrato_multiples_errores(entrada_valida: dict) -> None:
    """Varios campos inválidos → lista de errores con todos los problemas."""
    entrada_valida["id_producto"] = 0
    entrada_valida["nombre_producto"] = ""
    valido, errores = validar_contrato(entrada_valida)
    assert valido is False
    assert len(errores) >= 2
