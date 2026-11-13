"""
Pruebas del HITL nativo del Deep Agent (interrupt_on) con un modelo falso: sin Groq ni red.
"""
from __future__ import annotations

import uuid

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langgraph.types import Command

import botica.deep_agents.supervisor as sup


class ModeloFalso(GenericFakeChatModel):
    """Modelo de chat con respuestas fijas que acepta herramientas (bind_tools)."""

    def bind_tools(self, tools, **kwargs):
        return self


def _agente(monkeypatch, llamadas: list):
    respuestas = iter([
        AIMessage(content="", tool_calls=[{
            "name": "generar_solicitud_abastecimiento", "id": "llamada-1",
            "args": {"id_producto": 31, "sede": "Sede Bolognesi 606", "responsable": "Prueba"},
        }]),
        AIMessage(content="Listo."),
    ])

    def ejecutar_falso(entrada: dict) -> dict:
        llamadas.append(entrada)
        return {"prioridad": "alta", "propuesta": {"cantidad_solicitada": 40},
                "resultado_validacion": "APROBADO", "decision_hitl": "AUTO_BORRADOR",
                "codigo_solicitud": "SOL-PRUEBA", "ya_procesada": False, "solicitud_registrada": {"x": 1}}

    monkeypatch.setattr(sup, "ejecutar_solicitud", ejecutar_falso)
    return sup.crear_supervisor(modelo=ModeloFalso(messages=respuestas),
                                modelo_subagente=ModeloFalso(messages=iter([])))


def _hasta_interrupcion(agente):
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    r = agente.invoke({"messages": [{"role": "user", "content": "Revisa el stock"}]}, config=config)
    assert r.get("__interrupt__"), "el agente debía pausarse antes de generar la solicitud"
    pedido = r["__interrupt__"][0].value["action_requests"][0]
    assert pedido["name"] == "generar_solicitud_abastecimiento"
    return config


def test_rechazo_humano_no_genera_solicitud(monkeypatch):
    llamadas: list = []
    agente = _agente(monkeypatch, llamadas)
    config = _hasta_interrupcion(agente)

    final = agente.invoke(Command(resume={"decisions": [{"type": "reject", "message": "No aprobado"}]}), config=config)

    assert llamadas == []  # el flujo multiagente nunca se ejecutó
    informe = sup.informe_desde_herramientas(final["messages"])
    assert len(informe) == 1
    assert informe[0]["registro"] == "NO REGISTRADA"
    assert informe[0]["decision_hitl"] == "RECHAZADA por la persona"


def test_aprobacion_humana_ejecuta_y_el_informe_sale_de_la_herramienta(monkeypatch):
    llamadas: list = []
    agente = _agente(monkeypatch, llamadas)
    config = _hasta_interrupcion(agente)

    final = agente.invoke(Command(resume={"decisions": [{"type": "approve"}]}), config=config)

    assert len(llamadas) == 1 and llamadas[0]["id_producto"] == 31
    informe = sup.informe_desde_herramientas(final["messages"])
    assert informe[0]["codigo_solicitud"] == "SOL-PRUEBA"
    assert informe[0]["registro"] == "NUEVA"
    assert informe[0]["producto"] == "Amoxicilina 500 mg"  # dato real del inventario, no del LLM
