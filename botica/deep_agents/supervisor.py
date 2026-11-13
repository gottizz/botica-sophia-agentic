"""
Deep Agent · Supervisor de Abastecimiento (librería deepagents, construida sobre LangGraph).

A diferencia del Orquestador (StateGraph de orden fijo), este agente:
  1. Planifica su trabajo escribiendo un plan en /todos.md (sistema de archivos integrado).
  2. Delega en el subagente "analista-inventario" (herramienta integrada task) la revisión del stock.
  3. Ejecuta el flujo multiagente existente (A01 → A02 → A03 → HITL) para cada producto con
     stock bajo, mediante la herramienta generar_solicitud_abastecimiento.
  4. Antes de cada generar_solicitud_abastecimiento se detiene (interrupt_on) y espera la
     aprobación humana de la asistente administrativa: HITL nativo de LangGraph.
  5. Escribe su informe en el sistema de archivos virtual (write_file).

El informe que se entrega al usuario NO es el texto del LLM: informe_desde_herramientas() lo
arma con los resultados reales de generar_solicitud_abastecimiento (y marca las rechazadas).

Nunca ejecuta compras: solo genera solicitudes de abastecimiento.
"""
from __future__ import annotations

import json
import os
from datetime import date

from deepagents import create_deep_agent
from dotenv import load_dotenv
from langchain_core.tools import tool
from langchain_groq import ChatGroq
from langgraph.checkpoint.memory import MemorySaver

from botica.herramientas.consultar_inventario import _RUTA_INVENTARIO
from botica.orquestador.grafo import ejecutar_solicitud

load_dotenv()

# Modelo del Deep Agent: distinto al de los agentes A01-A03 para no compartir el cupo de tokens de Groq
MODELO_SUPERVISOR = os.getenv("GROQ_MODEL_SUPERVISOR", "openai/gpt-oss-120b")
# El subagente usa otro modelo: en Groq cada modelo tiene su propio cupo de tokens por minuto
MODELO_SUBAGENTE = os.getenv("GROQ_MODEL_SUBAGENTE", "openai/gpt-oss-20b")
# Reintentos con espera ante el límite de la capa gratuita (error 429)
REINTENTOS = 8


@tool
def listar_inventario(sede: str) -> list[dict]:
    """Devuelve todos los productos del inventario de una sede con su stock disponible y mínimo."""
    inventario = json.loads(_RUTA_INVENTARIO.read_text(encoding="utf-8"))
    sede_norm = sede.strip().lower()
    return [r for r in inventario if r.get("sede", "").strip().lower() == sede_norm]


@tool
def generar_solicitud_abastecimiento(id_producto: int, sede: str, responsable: str) -> dict:
    """
    Ejecuta el flujo multiagente de Botica Sophia (A01 Inventario → A02 Abastecimiento →
    A03 Validador → compuerta HITL) para un producto y devuelve la decisión y el código de solicitud.
    """
    inventario = json.loads(_RUTA_INVENTARIO.read_text(encoding="utf-8"))
    registro = next(
        (r for r in inventario
         if r["id_producto"] == id_producto and r["sede"].strip().lower() == sede.strip().lower()),
        None,
    )
    if registro is None:
        return {"error": f"Producto {id_producto} no existe en la sede '{sede}'."}

    resultado = ejecutar_solicitud({
        "id_producto": registro["id_producto"],
        "nombre_producto": registro["nombre_producto"],
        "cantidad_disponible": registro["cantidad_disponible"],
        "stock_minimo": registro["stock_minimo"],
        "cantidad_solicitada": None,
        "sede": registro["sede"],
        "fecha_solicitud": date.today().isoformat(),
        "responsable": responsable,
    })
    return {
        "id_producto": registro["id_producto"],
        "producto": registro["nombre_producto"],
        "prioridad": resultado.get("prioridad"),
        # Si ya estaba registrada, la cantidad sale de la solicitud existente (no se volvió a validar)
        "cantidad_solicitada": (resultado.get("propuesta") or resultado.get("solicitud_registrada") or {}).get("cantidad_solicitada"),
        "resultado_validacion": resultado.get("resultado_validacion") or ("ya validada" if resultado.get("ya_procesada") else None),
        "decision_hitl": resultado.get("decision_hitl") or ("no aplica (duplicado)" if resultado.get("ya_procesada") else None),
        "codigo_solicitud": resultado.get("codigo_solicitud"),
        "registro": "YA_PROCESADA" if resultado.get("ya_procesada") else (
            "NUEVA" if resultado.get("solicitud_registrada") else "SIN_REGISTRO"),
    }


SUBAGENTE_ANALISTA = {
    "name": "analista-inventario",
    "description": (
        "Revisa el inventario de una sede y devuelve la lista de productos que requieren "
        "reposición (cantidad_disponible <= stock_minimo), con su id y prioridad."
    ),
    "system_prompt": (
        "Eres el analista de inventario de Botica Sophia. Usa listar_inventario y aplica la regla: "
        "requiere reposición si cantidad_disponible <= stock_minimo; prioridad 'alta' si está por "
        "debajo del mínimo, 'media' si está justo en el mínimo. Responde solo con la lista de "
        "productos que requieren reposición (id_producto, nombre, disponible, mínimo, prioridad). "
        "No inventes productos ni cantidades."
    ),
    "tools": [listar_inventario],
}

PROMPT_SUPERVISOR = (
    "Eres el Supervisor de Abastecimiento de Botica Sophia (Corporación Peruana de Salud C y L E.I.R.L.). "
    "Tu objetivo: detectar los productos con stock bajo de una sede y generar sus solicitudes de "
    "abastecimiento. Pasos obligatorios:\n"
    "1. Planifica: escribe tu lista de tareas en /todos.md con write_file y actualízala al terminar.\n"
    "2. Delega en el subagente 'analista-inventario' (herramienta task) la detección de stock bajo.\n"
    "3. Llama a generar_solicitud_abastecimiento una vez por cada producto que requiera reposición.\n"
    "4. Escribe el informe en /informe_abastecimiento.md con write_file: tabla con producto, prioridad, "
    "cantidad, validación, decisión HITL y código de solicitud.\n"
    "Si la persona RECHAZA una llamada a generar_solicitud_abastecimiento, esa decisión es final: "
    "no vuelvas a pedir la solicitud de ese producto y regístralo como rechazado en el informe.\n"
    "Reglas: nunca ejecutes compras, no elijas proveedores ni inventes precios. "
    "Usa solo los datos que devuelven las herramientas. Responde en español y de forma breve."
)


def crear_supervisor(modelo=None, modelo_subagente=None, checkpointer=None):
    """
    Crea el Deep Agent con planificación, subagente, sistema de archivos y HITL nativo.
    Los modelos son inyectables: las pruebas usan un modelo falso y no llaman a Groq.
    """
    modelo = modelo or ChatGroq(model=MODELO_SUPERVISOR, max_tokens=1500, max_retries=REINTENTOS)
    modelo_subagente = modelo_subagente or ChatGroq(
        model=MODELO_SUBAGENTE, max_tokens=1500, max_retries=REINTENTOS
    )
    return create_deep_agent(
        model=modelo,
        tools=[generar_solicitud_abastecimiento],
        system_prompt=PROMPT_SUPERVISOR,
        subagents=[{**SUBAGENTE_ANALISTA, "model": modelo_subagente}],
        interrupt_on={"generar_solicitud_abastecimiento": True},
        checkpointer=checkpointer or MemorySaver(),
        name="Supervisor de Abastecimiento (Deep Agent)",
    )


def informe_desde_herramientas(mensajes: list) -> list[dict]:
    """
    Arma el informe con los resultados REALES de generar_solicitud_abastecimiento.
    Recorre las llamadas a la herramienta que hizo el agente y su respuesta (ToolMessage).
    Si la persona rechazó la llamada en la compuerta HITL, la fila queda como RECHAZADA.
    """
    respuestas = {getattr(m, "tool_call_id", None): m for m in mensajes if m.type == "tool"}
    filas = []
    for m in mensajes:
        for llamada in getattr(m, "tool_calls", None) or []:
            if llamada["name"] != "generar_solicitud_abastecimiento":
                continue
            respuesta = respuestas.get(llamada["id"])
            datos = None
            if respuesta is not None and getattr(respuesta, "status", "success") != "error":
                try:
                    datos = json.loads(respuesta.content)
                except (TypeError, ValueError):
                    datos = None
            if datos is None or "error" in datos:
                filas.append({"id_producto": llamada["args"].get("id_producto"), "producto": "-",
                              "prioridad": "-", "cantidad_solicitada": "-", "resultado_validacion": "-",
                              "decision_hitl": "RECHAZADA por la persona" if datos is None else "ERROR",
                              "codigo_solicitud": "-", "registro": "NO REGISTRADA"})
            else:
                filas.append(datos)
    return filas


def tabla_markdown(filas: list[dict]) -> str:
    """Convierte las filas del informe en una tabla Markdown."""
    columnas = ["id_producto", "producto", "prioridad", "cantidad_solicitada",
                "resultado_validacion", "decision_hitl", "codigo_solicitud", "registro"]
    lineas = ["| " + " | ".join(columnas) + " |", "|" + "---|" * len(columnas)]
    lineas += ["| " + " | ".join(str(f.get(c, "-")) for c in columnas) + " |" for f in filas]
    return "\n".join(lineas)
