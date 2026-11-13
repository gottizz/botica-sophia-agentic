"""
Pruebas del Agente A02 (Abastecimiento).
Usa monkeypatch para reemplazar crear_llm con LLMFalso.
NUNCA se llama al LLM real.
"""
from __future__ import annotations

import pytest

from botica.estado.esquemas import PropuestaAbastecimiento


def _estado_con_a01(datos_base: dict, requiere: bool = True) -> dict:
    """Construye un estado que simula que A01 ya ejecutó."""
    return {
        **datos_base,
        "estado_proceso": "ok",
        "mensaje_error": None,
        "requiere_reposicion": requiere,
        "prioridad": "alta" if requiere else "baja",
        "cantidad_sugerida": 22 if requiere else 0,
        "analisis_inventario": "Análisis de prueba.",
        "propuesta": None,
        "resultado_validacion": None,
        "observaciones_validador": None,
        "decision_hitl": None,
        "clave_idempotencia": None,
        "codigo_solicitud": None,
        "ya_procesada": None,
        "solicitud_existente": None,
        "solicitud_registrada": None,
        "errores": [],
        "trazas": [],
        "alertas": [],
    }


def test_a02_estructura_propuesta_cuando_requiere(
    monkeypatch: pytest.MonkeyPatch,
    llm_falso,
    datos_base: dict,
) -> None:
    """Cuando requiere_reposicion=True, A02 estructura la propuesta."""
    estado = _estado_con_a01(datos_base, requiere=True)

    propuesta_esperada = PropuestaAbastecimiento(
        producto="Paracetamol 500 mg",
        sede="Sede Bolognesi 606",
        cantidad_solicitada=22,
        prioridad="alta",
        tipo_solicitud="Reposición",
        observaciones="Stock crítico. Se requiere reposición urgente.",
    )
    llm_falso.configurar(PropuestaAbastecimiento, propuesta_esperada)
    monkeypatch.setattr("botica.agentes.a02_abastecimiento.crear_llm", lambda: llm_falso)

    from botica.agentes.a02_abastecimiento import nodo_a02_abastecimiento
    resultado = nodo_a02_abastecimiento(estado)

    assert "propuesta" in resultado
    assert resultado["propuesta"] is not None
    assert resultado["propuesta"]["cantidad_solicitada"] == 22
    assert resultado["propuesta"]["tipo_solicitud"] == "Reposición"
    assert resultado["estado_proceso"] == "ok"


def test_a02_usa_cantidad_sugerida_cuando_no_hay_cantidad_usuario(
    monkeypatch: pytest.MonkeyPatch,
    llm_falso,
    datos_base: dict,
) -> None:
    """Si el usuario no envió cantidad_solicitada, A02 usa cantidad_sugerida de A01."""
    estado = _estado_con_a01(datos_base, requiere=True)
    estado["cantidad_solicitada"] = None  # Usuario no envió cantidad
    estado["cantidad_sugerida"] = 22

    propuesta_esperada = PropuestaAbastecimiento(
        producto="Paracetamol 500 mg",
        sede="Sede Bolognesi 606",
        cantidad_solicitada=22,  # Debe usar la sugerida
        prioridad="alta",
        tipo_solicitud="Reposición",
        observaciones="Cantidad calculada automáticamente.",
    )
    llm_falso.configurar(PropuestaAbastecimiento, propuesta_esperada)
    monkeypatch.setattr("botica.agentes.a02_abastecimiento.crear_llm", lambda: llm_falso)

    from botica.agentes.a02_abastecimiento import nodo_a02_abastecimiento
    resultado = nodo_a02_abastecimiento(estado)

    # La cantidad en la propuesta debe ser la sugerida (22)
    assert resultado["propuesta"]["cantidad_solicitada"] == 22


def test_a02_usa_cantidad_del_usuario_cuando_la_envio(
    monkeypatch: pytest.MonkeyPatch,
    llm_falso,
    datos_base: dict,
) -> None:
    """Si el usuario envió cantidad_solicitada, A02 usa esa cantidad."""
    estado = _estado_con_a01(datos_base, requiere=True)
    estado["cantidad_solicitada"] = 30  # Usuario envió 30 explícitamente
    estado["cantidad_sugerida"] = 22

    propuesta_esperada = PropuestaAbastecimiento(
        producto="Paracetamol 500 mg",
        sede="Sede Bolognesi 606",
        cantidad_solicitada=30,  # Debe usar la del usuario
        prioridad="alta",
        tipo_solicitud="Reposición",
        observaciones="Cantidad solicitada por el responsable.",
    )
    llm_falso.configurar(PropuestaAbastecimiento, propuesta_esperada)
    monkeypatch.setattr("botica.agentes.a02_abastecimiento.crear_llm", lambda: llm_falso)

    from botica.agentes.a02_abastecimiento import nodo_a02_abastecimiento
    resultado = nodo_a02_abastecimiento(estado)

    # La cantidad debe ser la del usuario (30), no la sugerida (22)
    assert resultado["propuesta"]["cantidad_solicitada"] == 30


def test_a02_no_requiere_retorna_no_requiere(
    monkeypatch: pytest.MonkeyPatch,
    llm_falso,
    datos_base: dict,
) -> None:
    """Cuando requiere_reposicion=False, A02 retorna decision_hitl=NO_REQUIERE sin llamar al LLM."""
    estado = _estado_con_a01(datos_base, requiere=False)
    monkeypatch.setattr("botica.agentes.a02_abastecimiento.crear_llm", lambda: llm_falso)

    from botica.agentes.a02_abastecimiento import nodo_a02_abastecimiento
    resultado = nodo_a02_abastecimiento(estado)

    assert resultado["decision_hitl"] == "NO_REQUIERE"
    assert resultado.get("propuesta") is None
    assert resultado["estado_proceso"] == "ok"
