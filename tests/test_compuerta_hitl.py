"""
Pruebas de la compuerta HITL (Human-In-The-Loop).
Verifica los tres caminos de decisión: AUTO_BORRADOR, REVISION_HUMANA, ESCALAR.
"""
from __future__ import annotations

import pytest

from botica.politica.compuerta_hitl import decidir_hitl


def _estado_base() -> dict:
    """Estado mínimo válido con todos los campos necesarios."""
    return {
        "estado_proceso": "ok",
        "requiere_reposicion": True,
        "resultado_validacion": "APROBADO",
        "decision_hitl": None,
        "propuesta": {
            "producto": "Paracetamol 500 mg",
            "sede": "Sede Bolognesi 606",
            "cantidad_solicitada": 22,
            "prioridad": "alta",
            "tipo_solicitud": "Reposición",
            "observaciones": "Stock crítico.",
        },
    }


def test_auto_borrador_cuando_todo_ok() -> None:
    """estado_proceso=ok + requiere=True + APROBADO → AUTO_BORRADOR."""
    estado = _estado_base()
    assert decidir_hitl(estado) == "AUTO_BORRADOR"


def test_revision_humana_cuando_observado() -> None:
    """resultado_validacion=OBSERVADO → REVISION_HUMANA."""
    estado = _estado_base()
    estado["resultado_validacion"] = "OBSERVADO"
    assert decidir_hitl(estado) == "REVISION_HUMANA"


def test_escalar_cuando_error_sistema() -> None:
    """estado_proceso=error_sistema → ESCALAR."""
    estado = _estado_base()
    estado["estado_proceso"] = "error_sistema"
    assert decidir_hitl(estado) == "ESCALAR"


def test_escalar_cuando_error_transitorio() -> None:
    """estado_proceso=error_transitorio → ESCALAR."""
    estado = _estado_base()
    estado["estado_proceso"] = "error_transitorio"
    assert decidir_hitl(estado) == "ESCALAR"


def test_escalar_cuando_error_datos() -> None:
    """estado_proceso=error_datos (datos contradictorios) → ESCALAR."""
    estado = _estado_base()
    estado["estado_proceso"] = "error_datos"
    assert decidir_hitl(estado) == "ESCALAR"


def test_revision_humana_cuando_no_requiere_pero_aprobado() -> None:
    """requiere_reposicion=False + APROBADO → REVISION_HUMANA (no hay propuesta válida para no-reposición)."""
    estado = _estado_base()
    estado["requiere_reposicion"] = False
    # No hay propuesta cuando no requiere reposición
    estado["propuesta"] = None
    # No debe ser AUTO_BORRADOR porque requiere_reposicion=False
    resultado = decidir_hitl(estado)
    # Con requiere_reposicion=False y no decision_hitl=NO_REQUIERE, cae en REVISION_HUMANA
    assert resultado == "REVISION_HUMANA"


def test_no_requiere_si_decision_previa() -> None:
    """Si ya se marcó decision_hitl=NO_REQUIERE, la compuerta respeta esa decisión."""
    estado = _estado_base()
    estado["decision_hitl"] = "NO_REQUIERE"
    assert decidir_hitl(estado) == "NO_REQUIERE"


def test_revision_humana_sin_propuesta() -> None:
    """requiere_reposicion=True pero propuesta=None → REVISION_HUMANA."""
    estado = _estado_base()
    estado["propuesta"] = None
    assert decidir_hitl(estado) == "REVISION_HUMANA"


# ---------------------------------------------------------------------------
# Corrección 2: datos contradictorios → ESCALAR
# ---------------------------------------------------------------------------

def test_escalar_cuando_datos_contradictorios() -> None:
    """A01 marcó datos contradictorios → ESCALAR aunque el resto parezca correcto."""
    estado = _estado_base()
    estado["datos_contradictorios"] = True
    estado["estado_proceso"] = "datos_contradictorios"
    assert decidir_hitl(estado) == "ESCALAR"


def test_escalar_con_solo_la_marca_de_contradiccion() -> None:
    """La marca datos_contradictorios basta para escalar, incluso con validador APROBADO."""
    estado = _estado_base()
    estado["datos_contradictorios"] = True
    assert decidir_hitl(estado) == "ESCALAR"


def test_sin_contradiccion_sigue_auto_borrador() -> None:
    """datos_contradictorios=False no altera la decisión AUTO_BORRADOR."""
    estado = _estado_base()
    estado["datos_contradictorios"] = False
    assert decidir_hitl(estado) == "AUTO_BORRADOR"
