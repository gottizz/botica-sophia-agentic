"""
Agente A02 - Abastecimiento: estructura la propuesta de reposición.
Si el usuario no envió cantidad_solicitada, usa cantidad_sugerida de A01.
"""
from __future__ import annotations

import time

from botica.agentes.base import crear_llm, crear_plantilla
from botica.estado.esquemas import EstadoAbastecimiento, PropuestaAbastecimiento
from botica.reglas.errores import ClaseError, ErrorProceso, clasificar_error, registrar_error

from pathlib import Path
_RUTA_ERRORES = str(Path(__file__).parent.parent.parent / "conocimiento" / "datos" / "cola_errores.json")


def nodo_a02_abastecimiento(estado: EstadoAbastecimiento) -> dict:
    """
    Nodo del grafo: Agente A02 - Abastecimiento.

    - Si requiere_reposicion == False, marca NO_REQUIERE y termina.
    - Si requiere reposición, usa cantidad_final = cantidad_solicitada (del usuario)
      o cantidad_sugerida (de A01), luego llama al LLM para estructurar la propuesta.
    """
    inicio = time.monotonic()
    nombre_nodo = "a02_abastecimiento"

    requiere_reposicion = estado.get("requiere_reposicion", False)

    # Si no requiere reposición, terminamos sin estructurar propuesta
    if not requiere_reposicion:
        duracion = (time.monotonic() - inicio) * 1000
        return {
            "decision_hitl": "NO_REQUIERE",
            "estado_proceso": "ok",
            "errores": [],
            "trazas": [{
                "nodo": nombre_nodo,
                "duracion_ms": round(duracion, 2),
                "resultado": "NO_REQUIERE",
            }],
            "alertas": [],
        }

    # Determinar cantidad final: la del usuario o la sugerida por A01
    cantidad_usuario = estado.get("cantidad_solicitada")
    cantidad_sugerida = estado.get("cantidad_sugerida", 0)
    cantidad_final = cantidad_usuario if cantidad_usuario else cantidad_sugerida

    nombre_producto = estado["nombre_producto"]
    sede = estado["sede"]
    prioridad = estado.get("prioridad", "alta")
    analisis = estado.get("analisis_inventario", "")

    try:
        prompt_sistema = (
            "Eres el Agente de Abastecimiento de Botica Sophia. "
            "Tu tarea es estructurar una propuesta de reposición con los datos que te proporcionan. "
            "NO elijas proveedores, NO inventes precios ni condiciones comerciales. "
            "El tipo_solicitud SIEMPRE es 'Reposición'."
        )
        prompt_usuario = (
            f"Producto: {nombre_producto}\n"
            f"Sede: {sede}\n"
            f"Cantidad solicitada: {cantidad_final} unidades\n"
            f"Prioridad: {prioridad}\n"
            f"Análisis de inventario: {analisis}\n\n"
            "Estructura la propuesta de abastecimiento con los campos: "
            "producto (str), sede (str), cantidad_solicitada (int), "
            "prioridad (str), tipo_solicitud (str = 'Reposición'), observaciones (str)."
        )

        # Cadena LCEL: plantilla de prompt | modelo con salida estructurada (Pydantic)
        llm = crear_llm()
        cadena = (
            crear_plantilla(prompt_sistema)
            | llm.with_structured_output(PropuestaAbastecimiento)
        ).with_config(run_name="A02 · Agente de Abastecimiento")
        salida: PropuestaAbastecimiento = cadena.invoke({"entrada": prompt_usuario})

        # Forzar cantidad_final aunque el LLM ponga otra cosa
        propuesta = salida.model_dump()
        propuesta["cantidad_solicitada"] = cantidad_final

        duracion = (time.monotonic() - inicio) * 1000

        return {
            "propuesta": propuesta,
            "estado_proceso": "ok",
            "errores": [],
            "trazas": [{
                "nodo": nombre_nodo,
                "duracion_ms": round(duracion, 2),
                "resultado": "ok",
                "cantidad_final": cantidad_final,
            }],
            "alertas": [],
        }

    except Exception as exc:
        clase = clasificar_error(exc)
        mensaje_error = f"{type(exc).__name__}: {exc}"
        error = ErrorProceso(
            nodo=nombre_nodo,
            clase_error=clase,
            mensaje=mensaje_error,
            carga_original=dict(estado),
        )
        registrar_error(error, _RUTA_ERRORES)
        duracion = (time.monotonic() - inicio) * 1000

        estado_proceso = (
            "error_transitorio" if clase == ClaseError.TRANSITORIO
            else "error_datos" if clase == ClaseError.DATOS
            else "error_sistema"
        )

        return {
            "estado_proceso": estado_proceso,
            "mensaje_error": mensaje_error,
            "errores": [{"nodo": nombre_nodo, "mensaje": mensaje_error}],
            "trazas": [{
                "nodo": nombre_nodo,
                "duracion_ms": round(duracion, 2),
                "resultado": estado_proceso,
            }],
            "alertas": [],
        }
