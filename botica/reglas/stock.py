"""
Reglas deterministas de stock: reposición, prioridad y cantidad sugerida.
Sin LLM. Implementa la lógica definida en CLAUDE.md.
"""
from __future__ import annotations


def determinar_reposicion(disponible: int, minimo: int) -> bool:
    """True si el stock disponible está en o por debajo del mínimo."""
    return disponible <= minimo


def calcular_prioridad(disponible: int, minimo: int) -> str:
    """
    Determina la prioridad de reposición.

    - "alta"  si disponible < minimo  (incluye disponible == 0)
    - "media" si disponible == minimo
    - "baja"  si disponible > minimo  (no requiere reposición)
    """
    if disponible < minimo:
        return "alta"
    elif disponible == minimo:
        return "media"
    else:
        return "baja"


def calcular_cantidad_sugerida(disponible: int, minimo: int) -> int:
    """
    Calcula la cantidad sugerida para reponer.
    Fórmula: stock_minimo * 2 - cantidad_disponible si requiere reposición; si no, 0.
    """
    if not determinar_reposicion(disponible, minimo):
        return 0
    return minimo * 2 - disponible
