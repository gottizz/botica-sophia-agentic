"""
Agente A01 - Inventario: consulta el stock real y determina si se requiere reposición.
Usa la herramienta consultar_inventario y estructura la salida con SalidaInventario.
El LLM NO inventa datos; usa SOLO los datos del inventario.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

from botica.agentes.base import crear_llm, crear_plantilla
from botica.estado.esquemas import EstadoAbastecimiento, RedaccionInventario, SalidaInventario
from botica.herramientas.consultar_inventario import consultar_inventario
from botica.reglas.errores import ClaseError, ErrorProceso, clasificar_error, registrar_error
from botica.reglas.stock import calcular_cantidad_sugerida, calcular_prioridad, determinar_reposicion

# Ruta del archivo de errores (se puede sobrescribir en tests vía monkeypatch)
from pathlib import Path
_RUTA_ERRORES = str(Path(__file__).parent.parent.parent / "conocimiento" / "datos" / "cola_errores.json")
_RUTA_TRAZAS = str(Path(__file__).parent.parent.parent / "conocimiento" / "datos" / "trazas.json")


def nodo_a01_inventario(estado: EstadoAbastecimiento) -> dict:
    """
    Nodo del grafo: Agente A01 - Análisis de Inventario.

    1. Consulta el inventario real con la herramienta consultar_inventario.
    2. Calcula requiere_reposicion, prioridad y cantidad_sugerida con las reglas deterministas.
    3. Si el stock informado no coincide con el inventario, marca datos_contradictorios.
    4. Si no, llama al LLM solo para redactar el análisis.
    """
    inicio = time.monotonic()
    nombre_nodo = "a01_inventario"

    id_producto = estado["id_producto"]
    sede = estado["sede"]
    disponible_informado = estado["cantidad_disponible"]
    stock_minimo = estado["stock_minimo"]
    nombre_producto = estado["nombre_producto"]

    try:
        # Llamada directa a la herramienta (no como ReAct loop)
        resultado_inventario = consultar_inventario.invoke(
            {"id_producto": id_producto, "sede": sede}
        )

        # Si la herramienta retorna un error, lo registramos
        if "error" in resultado_inventario:
            mensaje_error = resultado_inventario["error"]
            error = ErrorProceso(
                nodo=nombre_nodo,
                clase_error=ClaseError.DATOS,
                mensaje=mensaje_error,
                carga_original=dict(estado),
            )
            registrar_error(error, _RUTA_ERRORES)
            duracion = (time.monotonic() - inicio) * 1000
            return {
                "estado_proceso": "error_datos",
                "mensaje_error": mensaje_error,
                "errores": [{"nodo": nombre_nodo, "mensaje": mensaje_error}],
                "trazas": [{
                    "nodo": nombre_nodo,
                    "duracion_ms": round(duracion, 2),
                    "resultado": "error_datos",
                }],
            }

        # Calcular con reglas deterministas (fuente de verdad)
        disponible_real = resultado_inventario.get("cantidad_disponible", disponible_informado)
        minimo_real = resultado_inventario.get("stock_minimo", stock_minimo)

        requiere = determinar_reposicion(disponible_real, minimo_real)
        prioridad = calcular_prioridad(disponible_real, minimo_real)
        sugerida = calcular_cantidad_sugerida(disponible_real, minimo_real)

        # Datos contradictorios: el stock informado no coincide con el inventario real.
        # No se llama al LLM; la compuerta HITL decide ESCALAR.
        discrepancias: list[str] = []
        if disponible_informado != disponible_real:
            discrepancias.append(
                f"cantidad_disponible informada={disponible_informado}, inventario={disponible_real}"
            )
        if stock_minimo != minimo_real:
            discrepancias.append(
                f"stock_minimo informado={stock_minimo}, inventario={minimo_real}"
            )
        if discrepancias:
            mensaje = "Datos contradictorios con el inventario: " + "; ".join(discrepancias)
            duracion = (time.monotonic() - inicio) * 1000
            return {
                "datos_contradictorios": True,
                "requiere_reposicion": requiere,
                "prioridad": prioridad,
                "cantidad_sugerida": sugerida,
                "estado_proceso": "datos_contradictorios",
                "mensaje_error": mensaje,
                "errores": [{"nodo": nombre_nodo, "mensaje": mensaje}],
                "trazas": [{
                    "nodo": nombre_nodo,
                    "duracion_ms": round(duracion, 2),
                    "resultado": "datos_contradictorios",
                }],
                "alertas": [],
            }

        # Construir prompt para el LLM (solo redacta el análisis)
        prompt_sistema = (
            "Eres el Agente de Inventario de Botica Sophia. "
            "Tu tarea es redactar el análisis del stock de un producto usando SOLO los datos reales del inventario. "
            "La reposición, la prioridad y la cantidad sugerida ya fueron calculadas por reglas deterministas: "
            "no las cambies ni las recalcules. "
            "NO inventes datos, precios, proveedores ni cantidades. "
            "Redacta un análisis conciso y profesional."
        )
        prompt_usuario = (
            f"Producto: {nombre_producto} (id={id_producto})\n"
            f"Sede: {sede}\n"
            f"Stock disponible: {disponible_real} unidades\n"
            f"Stock mínimo: {minimo_real} unidades\n"
            f"¿Requiere reposición?: {'Sí' if requiere else 'No'}\n"
            f"Prioridad determinada: {prioridad}\n"
            f"Cantidad sugerida: {sugerida} unidades\n\n"
            "Devuelve únicamente el campo analisis (str)."
        )

        # Cadena LCEL: plantilla de prompt | modelo con salida estructurada (Pydantic)
        llm = crear_llm()
        cadena = (
            crear_plantilla(prompt_sistema)
            | llm.with_structured_output(RedaccionInventario)
        ).with_config(run_name="A01 · Agente de Inventario")
        redaccion: RedaccionInventario = cadena.invoke({"entrada": prompt_usuario})

        # Los valores de las reglas son la fuente de verdad; el LLM solo aporta el análisis
        salida = SalidaInventario(
            requiere_reposicion=requiere,
            prioridad=prioridad,
            cantidad_sugerida=sugerida,
            analisis=redaccion.analisis,
        )

        duracion = (time.monotonic() - inicio) * 1000

        return {
            "datos_contradictorios": False,
            "requiere_reposicion": salida.requiere_reposicion,
            "prioridad": salida.prioridad,
            "cantidad_sugerida": salida.cantidad_sugerida,
            "analisis_inventario": salida.analisis,
            "estado_proceso": "ok",
            "errores": [],
            "trazas": [{
                "nodo": nombre_nodo,
                "duracion_ms": round(duracion, 2),
                "resultado": "ok",
                "prioridad": salida.prioridad,
                "requiere_reposicion": salida.requiere_reposicion,
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
            "errores": [{"nodo": nombre_nodo, "mensaje": mensaje_error, "clase": clase.value}],
            "trazas": [{
                "nodo": nombre_nodo,
                "duracion_ms": round(duracion, 2),
                "resultado": estado_proceso,
            }],
            "alertas": [],
        }
