"""
Pruebas del Agente A03 (Validador).
Usa monkeypatch para reemplazar crear_llm con LLMFalso.
NUNCA se llama al LLM real.
"""
from __future__ import annotations

import pytest

from botica.estado.esquemas import SalidaValidador


def _estado_con_propuesta(datos_base: dict) -> dict:
    """Estado que simula que A01 y A02 ya ejecutaron."""
    return {
        **datos_base,
        "estado_proceso": "ok",
        "mensaje_error": None,
        "requiere_reposicion": True,
        "prioridad": "alta",
        "cantidad_sugerida": 22,
        "analisis_inventario": "Stock crítico detectado.",
        "propuesta": {
            "producto": "Paracetamol 500 mg",
            "sede": "Sede Bolognesi 606",
            "cantidad_solicitada": 22,
            "prioridad": "alta",
            "tipo_solicitud": "Reposición",
            "observaciones": "Reposición urgente requerida.",
        },
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


def test_a03_propuesta_coherente_retorna_aprobado(
    monkeypatch: pytest.MonkeyPatch,
    llm_falso,
    datos_base: dict,
) -> None:
    """Propuesta coherente con el inventario → resultado APROBADO."""
    estado = _estado_con_propuesta(datos_base)

    salida_esperada = SalidaValidador(
        resultado="APROBADO",
        observaciones=["La propuesta es coherente con el inventario real."],
    )
    llm_falso.configurar(SalidaValidador, salida_esperada)
    monkeypatch.setattr("botica.agentes.a03_validador.crear_llm", lambda: llm_falso)

    from botica.agentes.a03_validador import nodo_a03_validador
    resultado = nodo_a03_validador(estado)

    assert resultado["resultado_validacion"] == "APROBADO"
    assert isinstance(resultado["observaciones_validador"], list)
    assert resultado["estado_proceso"] == "ok"


def test_a03_propuesta_observada_retorna_observado(
    monkeypatch: pytest.MonkeyPatch,
    llm_falso,
    datos_base: dict,
) -> None:
    """LLM devuelve OBSERVADO → resultado OBSERVADO con observaciones."""
    estado = _estado_con_propuesta(datos_base)

    salida_esperada = SalidaValidador(
        resultado="OBSERVADO",
        observaciones=[
            "La cantidad solicitada parece excesiva.",
            "Se recomienda revisión humana.",
        ],
    )
    llm_falso.configurar(SalidaValidador, salida_esperada)
    monkeypatch.setattr("botica.agentes.a03_validador.crear_llm", lambda: llm_falso)

    from botica.agentes.a03_validador import nodo_a03_validador
    resultado = nodo_a03_validador(estado)

    assert resultado["resultado_validacion"] == "OBSERVADO"
    assert len(resultado["observaciones_validador"]) == 2


def test_a03_omite_validacion_si_no_requiere(
    monkeypatch: pytest.MonkeyPatch,
    llm_falso,
    datos_base: dict,
) -> None:
    """Si decision_hitl=NO_REQUIERE, A03 no hace nada (no llama al LLM)."""
    estado = _estado_con_propuesta(datos_base)
    estado["decision_hitl"] = "NO_REQUIERE"
    estado["propuesta"] = None

    monkeypatch.setattr("botica.agentes.a03_validador.crear_llm", lambda: llm_falso)

    from botica.agentes.a03_validador import nodo_a03_validador
    resultado = nodo_a03_validador(estado)

    # No debe haber resultado_validacion
    assert resultado.get("resultado_validacion") is None
    assert resultado.get("observaciones_validador") is None
    # Debe incluir traza de que fue omitido
    assert len(resultado["trazas"]) > 0


def test_a03_sin_propuesta_retorna_observado(
    monkeypatch: pytest.MonkeyPatch,
    llm_falso,
    datos_base: dict,
) -> None:
    """Si no hay propuesta de A02, A03 retorna OBSERVADO directamente."""
    estado = _estado_con_propuesta(datos_base)
    estado["propuesta"] = None
    estado["decision_hitl"] = None

    monkeypatch.setattr("botica.agentes.a03_validador.crear_llm", lambda: llm_falso)

    from botica.agentes.a03_validador import nodo_a03_validador
    resultado = nodo_a03_validador(estado)

    assert resultado["resultado_validacion"] == "OBSERVADO"
    assert len(resultado["observaciones_validador"]) > 0


# ---------------------------------------------------------------------------
# Corrección 3: el prompt del Validador incluye las reglas y el responsable
# ---------------------------------------------------------------------------

def _prompt_enviado(llm_falso) -> tuple[str, str]:
    """Devuelve (prompt_sistema, prompt_usuario) de la única llamada al LLM falso."""
    assert len(llm_falso.llamadas) == 1
    mensajes = llm_falso.llamadas[0]
    return mensajes[0]["content"], mensajes[1]["content"]


def test_a03_prompt_incluye_reglas_y_responsable(
    monkeypatch: pytest.MonkeyPatch,
    llm_falso,
    datos_base: dict,
) -> None:
    """Paracetamol (8, 15, cantidad 22): el prompt explica la fórmula, las prioridades y el responsable."""
    estado = _estado_con_propuesta(datos_base)
    estado["cantidad_solicitada"] = 22

    llm_falso.configurar(SalidaValidador, SalidaValidador(resultado="APROBADO", observaciones=[]))
    monkeypatch.setattr("botica.agentes.a03_validador.crear_llm", lambda: llm_falso)

    from botica.agentes.a03_validador import nodo_a03_validador
    resultado = nodo_a03_validador(estado)
    sistema, usuario = _prompt_enviado(llm_falso)

    # Reglas del CLAUDE.md
    assert "stock_minimo * 2 - cantidad_disponible" in sistema
    assert "'alta' si cantidad_disponible < stock_minimo" in sistema
    assert "'media' si cantidad_disponible == stock_minimo" in sistema
    assert "'baja' si está por encima" in sistema
    # El responsable va en la entrada, no en la propuesta
    assert "NO es un campo de la propuesta" in sistema
    assert "Responsable: Juana Pérez" in usuario
    # Solo observa ante incumplimientos reales
    assert "OBSERVADO SOLO ante un incumplimiento real" in sistema
    # Valores esperados calculados con las reglas
    assert "Prioridad: alta" in usuario
    assert "15 * 2 - 8 = 22" in usuario
    assert "Cantidad solicitada esperada: 22" in usuario
    assert resultado["resultado_validacion"] == "APROBADO"


def test_a03_prompt_usa_sugerida_si_no_hay_cantidad_en_entrada(
    monkeypatch: pytest.MonkeyPatch,
    llm_falso,
    datos_base: dict,
) -> None:
    """Sin cantidad_solicitada en la entrada, la cantidad esperada es la sugerida por las reglas."""
    estado = _estado_con_propuesta(datos_base)
    estado.update({
        "id_producto": 34,
        "nombre_producto": "Omeprazol 20 mg",
        "cantidad_disponible": 12,
        "stock_minimo": 12,
        "cantidad_solicitada": None,
    })

    llm_falso.configurar(SalidaValidador, SalidaValidador(resultado="APROBADO", observaciones=[]))
    monkeypatch.setattr("botica.agentes.a03_validador.crear_llm", lambda: llm_falso)

    from botica.agentes.a03_validador import nodo_a03_validador
    nodo_a03_validador(estado)
    _, usuario = _prompt_enviado(llm_falso)

    assert "Prioridad: media" in usuario
    assert "12 * 2 - 12 = 12" in usuario
    assert "Cantidad solicitada en la entrada: no indicada" in usuario
    assert "Cantidad solicitada esperada: 12 (cantidad_sugerida" in usuario
