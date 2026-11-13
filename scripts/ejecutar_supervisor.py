"""
Ejecuta el Deep Agent Supervisor de Abastecimiento en la terminal.
Uso: uv run python scripts/ejecutar_supervisor.py "Sede Bolognesi 606" "Willian Polo"

Cuando el agente quiere generar una solicitud, LangGraph lo interrumpe (HITL) y la
persona responde en la terminal: s = aprobar, n = rechazar.
"""
from __future__ import annotations

import sys
import uuid

from langgraph.types import Command

from botica.deep_agents.supervisor import crear_supervisor, informe_desde_herramientas, tabla_markdown

sede = sys.argv[1] if len(sys.argv) > 1 else "Sede Bolognesi 606"
responsable = sys.argv[2] if len(sys.argv) > 2 else "Asistente administrativa"

agente = crear_supervisor()
config = {
    "configurable": {"thread_id": str(uuid.uuid4())},
    "run_name": "Supervisor de Abastecimiento (Deep Agent)",
    "recursion_limit": 60,
}
entrada = {"messages": [{"role": "user", "content": (
    f"Revisa el stock de la sede '{sede}' y genera las solicitudes de abastecimiento necesarias. "
    f"Responsable: {responsable}."
)}]}

print(f"\n=== Deep Agent · Supervisor de Abastecimiento · {sede} ===\n")
resultado = agente.invoke(entrada, config=config)

while resultado.get("__interrupt__"):
    pedido = resultado["__interrupt__"][0].value
    decisiones = []
    for accion in pedido["action_requests"]:
        print(f"⏸  HITL · el agente quiere ejecutar: {accion['name']}({accion['args']})")
        respuesta = input("   ¿Aprobar? (s/n): ").strip().lower()
        print(f"   → {'APROBADO' if respuesta == 's' else 'RECHAZADO'} por {responsable}\n")
        decisiones.append({"type": "approve"} if respuesta == "s"
                          else {"type": "reject", "message": "Rechazado por la asistente administrativa"})
    resultado = agente.invoke(Command(resume={"decisions": decisiones}), config=config)

print("=== Archivos del agente (plan /todos.md e informe) ===")
for ruta, archivo in (resultado.get("files") or {}).items():
    contenido = archivo["content"] if isinstance(archivo, dict) else archivo
    texto = "\n".join(contenido) if isinstance(contenido, list) else str(contenido)
    print(f"--- {ruta} ---\n{texto}\n")

print("=== Respuesta final del agente (texto del LLM) ===")
print(resultado["messages"][-1].content)

print("\n=== Informe verificado (armado desde los resultados reales de las herramientas) ===")
print(tabla_markdown(informe_desde_herramientas(resultado["messages"])))
