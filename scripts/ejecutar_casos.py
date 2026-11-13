"""
Ejecuta los casos de demostración del Orquestador LangGraph con el LLM real (Groq).
Con LANGSMITH_TRACING=true en el .env, cada ejecución queda registrada en LangSmith.
Uso: uv run python scripts/ejecutar_casos.py
"""
from __future__ import annotations

import time
from datetime import date

from dotenv import load_dotenv

load_dotenv()

from botica.orquestador.grafo import ejecutar_solicitud  # noqa: E402

HOY = date.today().isoformat()
BASE = {"sede": "Sede Bolognesi 606", "fecha_solicitud": HOY, "responsable": "Willian Polo",
        "cantidad_solicitada": None}
CASOS = [
    ("Stock bajo", {"id_producto": 25, "nombre_producto": "Paracetamol 500 mg", "cantidad_disponible": 8, "stock_minimo": 15}),
    ("Mismo envío otra vez", {"id_producto": 25, "nombre_producto": "Paracetamol 500 mg", "cantidad_disponible": 8, "stock_minimo": 15}),
    ("Stock suficiente", {"id_producto": 28, "nombre_producto": "Ibuprofeno 400 mg", "cantidad_disponible": 40, "stock_minimo": 15}),
    ("Justo en el mínimo", {"id_producto": 34, "nombre_producto": "Omeprazol 20 mg", "cantidad_disponible": 12, "stock_minimo": 12}),
    ("Producto inexistente", {"id_producto": 9999, "nombre_producto": "Producto X", "cantidad_disponible": 5, "stock_minimo": 10}),
]

for i, (nombre, datos) in enumerate(CASOS):
    if i:
        time.sleep(15)  # respeta el cupo gratuito de Groq (tokens por minuto)
    r = ejecutar_solicitud({**BASE, **datos})
    registro = r.get("solicitud_registrada") or {}
    print(f"\n[{i + 1}] {nombre} · id {datos['id_producto']} {datos['nombre_producto']}")
    print(f"    reposición: {r.get('requiere_reposicion')} · prioridad: {r.get('prioridad')}"
          f" · validación: {r.get('resultado_validacion')} · HITL: {r.get('decision_hitl')}")
    print(f"    código: {r.get('codigo_solicitud')} · ya_procesada: {r.get('ya_procesada')}"
          f" · estado: {registro.get('estado_solicitud', '-')}")
    if r.get("mensaje_error"):
        print(f"    error: {r['mensaje_error']}")
    print("    nodos: " + " → ".join(t["nodo"] for t in r.get("trazas", [])))
