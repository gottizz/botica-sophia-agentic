"""
Pruebas de las reglas deterministas de stock.
Usa los datos del inventario del CLAUDE.md como referencia.
"""
from __future__ import annotations

import pytest

from botica.reglas.stock import (
    calcular_cantidad_sugerida,
    calcular_prioridad,
    determinar_reposicion,
)


# Parámetros: (disponible, minimo, requiere, prioridad, sugerida)
CASOS_INVENTARIO = [
    (8,  15, True,  "alta",  22),   # Paracetamol: por debajo del mínimo
    (40, 15, False, "baja",  0),    # Ibuprofeno: stock suficiente
    (0,  20, True,  "alta",  40),   # Amoxicilina: sin stock
    (12, 12, True,  "media", 12),   # Omeprazol: justo en el mínimo
    (55, 10, False, "baja",  0),    # Loratadina: muy por encima
]


@pytest.mark.parametrize("disponible,minimo,esperado", [
    (8,  15, True),
    (40, 15, False),
    (0,  20, True),
    (12, 12, True),
    (55, 10, False),
])
def test_determinar_reposicion(disponible: int, minimo: int, esperado: bool) -> None:
    """determinar_reposicion: True si disponible <= minimo."""
    assert determinar_reposicion(disponible, minimo) == esperado


@pytest.mark.parametrize("disponible,minimo,esperado", [
    (8,  15, "alta"),
    (40, 15, "baja"),
    (0,  20, "alta"),
    (12, 12, "media"),
    (55, 10, "baja"),
])
def test_calcular_prioridad(disponible: int, minimo: int, esperado: str) -> None:
    """calcular_prioridad: alta/media/baja según la relación disponible-minimo."""
    assert calcular_prioridad(disponible, minimo) == esperado


def test_paracetamol_cantidad_sugerida() -> None:
    """Paracetamol (8 disp, 15 min) → sugerida = 15*2 - 8 = 22."""
    assert calcular_cantidad_sugerida(8, 15) == 22


def test_amoxicilina_cantidad_sugerida() -> None:
    """Amoxicilina (0 disp, 20 min) → sugerida = 20*2 - 0 = 40."""
    assert calcular_cantidad_sugerida(0, 20) == 40


def test_omeprazol_cantidad_sugerida() -> None:
    """Omeprazol (12 disp, 12 min) → sugerida = 12*2 - 12 = 12."""
    assert calcular_cantidad_sugerida(12, 12) == 12


def test_ibuprofeno_no_requiere() -> None:
    """Ibuprofeno (40 disp, 15 min) → no requiere reposición, prioridad baja."""
    assert not determinar_reposicion(40, 15)
    assert calcular_prioridad(40, 15) == "baja"


def test_loratadina_no_requiere() -> None:
    """Loratadina (55 disp, 10 min) → no requiere reposición, prioridad baja."""
    assert not determinar_reposicion(55, 10)
    assert calcular_prioridad(55, 10) == "baja"


def test_sin_stock_prioridad_alta() -> None:
    """Stock en cero → prioridad alta (incluye el caso de cero como < minimo)."""
    assert calcular_prioridad(0, 20) == "alta"
    assert determinar_reposicion(0, 20) is True


def test_disponible_igual_a_minimo_es_media() -> None:
    """Cuando disponible == minimo → prioridad media y requiere = True."""
    assert calcular_prioridad(10, 10) == "media"
    assert determinar_reposicion(10, 10) is True


@pytest.mark.parametrize("disponible,minimo,requiere,prioridad,sugerida", CASOS_INVENTARIO)
def test_casos_inventario(
    disponible: int, minimo: int, requiere: bool, prioridad: str, sugerida: int
) -> None:
    """Los tres valores de las reglas coinciden con los datos de prueba del CLAUDE.md."""
    assert determinar_reposicion(disponible, minimo) is requiere
    assert calcular_prioridad(disponible, minimo) == prioridad
    assert calcular_cantidad_sugerida(disponible, minimo) == sugerida


def test_cantidad_sugerida_es_cero_si_no_requiere() -> None:
    """Ibuprofeno (40 disp, 15 min) → no requiere → sugerida = 0 (antes devolvía -10)."""
    assert calcular_cantidad_sugerida(40, 15) == 0
    assert calcular_cantidad_sugerida(16, 15) == 0


def test_cantidad_sugerida_nunca_es_negativa() -> None:
    """Para cualquier combinación válida la cantidad sugerida es >= 0."""
    for minimo in range(1, 30):
        for disponible in range(0, 70):
            assert calcular_cantidad_sugerida(disponible, minimo) >= 0
