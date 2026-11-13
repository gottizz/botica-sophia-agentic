"""
Agente A03 - Validador: verifica que la propuesta sea coherente con el inventario.
Devuelve APROBADO u OBSERVADO con observaciones.
"""
from __future__ import annotations

import time

from botica.agentes.base import crear_llm, crear_plantilla
from botica.estado.esquemas import EstadoAbastecimiento, SalidaValidador
from botica.reglas.errores import ClaseError, ErrorProceso, clasificar_error, registrar_error
from botica.reglas.stock import calcular_cantidad_sugerida, calcular_prioridad

from pathlib import Path
_RUTA_ERRORES = str(Path(__file__).parent.parent.parent / "conocimiento" / "datos" / "cola_errores.json")


def nodo_a03_validador(estado: EstadoAbastecimiento) -> dict:
    """
    Nodo del grafo: Agente A03 - Validador.

    - Si decision_hitl == "NO_REQUIERE", no hay nada que validar.
    - Construye prompt con entrada original + propuesta de A02.
    - LLM verifica coherencia, ausencia de datos inventados y completitud.
    """
    inicio = time.monotonic()
    nombre_nodo = "a03_validador"

    # Si A02 determinó que no se requiere reposición, no hay nada que validar
    if estado.get("decision_hitl") == "NO_REQUIERE":
        duracion = (time.monotonic() - inicio) * 1000
        return {
            "errores": [],
            "trazas": [{
                "nodo": nombre_nodo,
                "duracion_ms": round(duracion, 2),
                "resultado": "omitido_no_requiere",
            }],
            "alertas": [],
        }

    propuesta = estado.get("propuesta")
    if propuesta is None:
        duracion = (time.monotonic() - inicio) * 1000
        return {
            "resultado_validacion": "OBSERVADO",
            "observaciones_validador": ["No se encontró propuesta de A02 para validar."],
            "errores": [],
            "trazas": [{
                "nodo": nombre_nodo,
                "duracion_ms": round(duracion, 2),
                "resultado": "OBSERVADO_sin_propuesta",
            }],
            "alertas": [],
        }

    disponible = estado["cantidad_disponible"]
    minimo = estado["stock_minimo"]
    cantidad_usuario = estado.get("cantidad_solicitada")
    # Valores esperados según las reglas deterministas (los mismos que usa A01)
    prioridad_esperada = calcular_prioridad(disponible, minimo)
    sugerida_esperada = calcular_cantidad_sugerida(disponible, minimo)
    cantidad_esperada = cantidad_usuario if cantidad_usuario else sugerida_esperada
    origen_cantidad = (
        "indicada por el responsable en la entrada" if cantidad_usuario
        else "cantidad_sugerida, porque la entrada no indicó cantidad_solicitada"
    )

    try:
        prompt_sistema = (
            "Eres el Agente Validador de Botica Sophia. "
            "Verifica la propuesta de abastecimiento SOLO contra estas reglas de negocio:\n"
            "- Requiere reposición si cantidad_disponible <= stock_minimo.\n"
            "- Prioridad: 'alta' si cantidad_disponible < stock_minimo (incluye stock en cero), "
            "'media' si cantidad_disponible == stock_minimo, 'baja' si está por encima.\n"
            "- cantidad_sugerida = stock_minimo * 2 - cantidad_disponible si requiere reposición; si no, 0.\n"
            "- cantidad_solicitada de la propuesta = la cantidad_solicitada de la entrada si se indicó; "
            "si no, la cantidad_sugerida. Cualquier entero > 0 indicado por el responsable es válido.\n"
            "- La propuesta debe tener: producto, sede, cantidad_solicitada, prioridad, "
            "tipo_solicitud = 'Reposición' y observaciones. El responsable viene en la entrada, "
            "NO es un campo de la propuesta.\n"
            "- La propuesta no debe incluir precios, proveedores ni condiciones comerciales.\n"
            "Devuelve APROBADO si la propuesta cumple estas reglas. Devuelve OBSERVADO SOLO ante un "
            "incumplimiento real de estas reglas, un dato faltante o un dato inventado, e indica en "
            "observaciones cuál regla se incumple. No observes por criterios ajenos a estas reglas."
        )
        prompt_usuario = (
            f"Datos de entrada originales:\n"
            f"  - Producto: {estado['nombre_producto']} (id={estado['id_producto']})\n"
            f"  - Sede: {estado['sede']}\n"
            f"  - Cantidad disponible: {disponible}\n"
            f"  - Stock mínimo: {minimo}\n"
            f"  - Cantidad solicitada en la entrada: "
            f"{cantidad_usuario if cantidad_usuario else 'no indicada'}\n"
            f"  - Responsable: {estado['responsable']}\n\n"
            f"Valores esperados según las reglas:\n"
            f"  - Prioridad: {prioridad_esperada}\n"
            f"  - Cantidad sugerida: {minimo} * 2 - {disponible} = {sugerida_esperada}\n"
            f"  - Cantidad solicitada esperada: {cantidad_esperada} ({origen_cantidad})\n\n"
            f"Propuesta de A02:\n{propuesta}\n\n"
            f"Análisis de A01: {estado.get('analisis_inventario', 'No disponible')}\n\n"
            "Valida la propuesta y devuelve: resultado ('APROBADO' o 'OBSERVADO') "
            "y observaciones (lista de strings)."
        )

        # Cadena LCEL: plantilla de prompt | modelo con salida estructurada (Pydantic)
        llm = crear_llm()
        cadena = (
            crear_plantilla(prompt_sistema)
            | llm.with_structured_output(SalidaValidador)
        ).with_config(run_name="A03 · Agente Validador")
        salida: SalidaValidador = cadena.invoke({"entrada": prompt_usuario})

        duracion = (time.monotonic() - inicio) * 1000

        return {
            "resultado_validacion": salida.resultado,
            "observaciones_validador": salida.observaciones,
            "estado_proceso": "ok",
            "errores": [],
            "trazas": [{
                "nodo": nombre_nodo,
                "duracion_ms": round(duracion, 2),
                "resultado": salida.resultado,
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
