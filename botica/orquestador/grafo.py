"""
Orquestador LangGraph: define y compila el StateGraph del sistema multiagente.
Flujo: validar_contrato → detectar_duplicado → A01 → A02 → A03 → compuerta HITL → registrar/encolar/escalar.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from langgraph.graph import END, START, StateGraph

from botica.agentes.a01_inventario import nodo_a01_inventario
from botica.agentes.a02_abastecimiento import nodo_a02_abastecimiento
from botica.agentes.a03_validador import nodo_a03_validador
from botica.estado.esquemas import EstadoAbastecimiento
from botica.herramientas.consultar_inventario import consultar_inventario
from botica.herramientas.registrar_solicitud import (
    encolar_revision,
    registrar_alerta,
    registrar_solicitud,
)
from botica.politica.compuerta_hitl import decidir_hitl
from botica.reglas.contrato import validar_contrato
from botica.reglas.errores import ClaseError, ErrorProceso, clasificar_error, registrar_error
from botica.reglas.idempotencia import calcular_clave, generar_codigo, verificar_idempotencia
from botica.reglas.stock import calcular_cantidad_sugerida, determinar_reposicion

# Rutas a los archivos de persistencia (relativas a la raíz del proyecto)
_RAIZ = Path(__file__).parent.parent.parent
_RUTA_SOLICITUDES = str(_RAIZ / "conocimiento" / "datos" / "solicitudes.json")
_RUTA_ALERTAS = str(_RAIZ / "conocimiento" / "datos" / "alertas.json")
_RUTA_COLA_REVISION = str(_RAIZ / "conocimiento" / "datos" / "cola_revision.json")
_RUTA_COLA_ERRORES = str(_RAIZ / "conocimiento" / "datos" / "cola_errores.json")


# ---------------------------------------------------------------------------
# Nodos del grafo
# ---------------------------------------------------------------------------

def nodo_validar_contrato(estado: EstadoAbastecimiento) -> dict:
    """Valida los 8 campos del contrato de entrada con reglas deterministas."""
    datos = {
        "id_producto": estado.get("id_producto"),
        "nombre_producto": estado.get("nombre_producto"),
        "cantidad_disponible": estado.get("cantidad_disponible"),
        "stock_minimo": estado.get("stock_minimo"),
        "cantidad_solicitada": estado.get("cantidad_solicitada"),
        "sede": estado.get("sede"),
        "fecha_solicitud": estado.get("fecha_solicitud"),
        "responsable": estado.get("responsable"),
    }

    valido, errores_lista = validar_contrato(datos)

    if valido:
        return {
            "estado_proceso": "ok",
            "errores": [],
            "trazas": [{"nodo": "validar_contrato", "resultado": "ok"}],
            "alertas": [],
        }
    else:
        mensaje = "; ".join(errores_lista)
        return {
            "estado_proceso": "error_datos",
            "mensaje_error": mensaje,
            "errores": [{"nodo": "validar_contrato", "mensaje": msg} for msg in errores_lista],
            "trazas": [{"nodo": "validar_contrato", "resultado": "error_datos"}],
            "alertas": [],
        }


def nodo_detectar_duplicado(estado: EstadoAbastecimiento) -> dict:
    """
    Verificación TEMPRANA de idempotencia, antes de llamar a los agentes LLM.

    La cantidad final no depende del LLM: es la cantidad_solicitada del responsable o la
    cantidad_sugerida de las reglas de stock (A02 la fuerza a ese valor). Por eso la misma
    clave SHA-256 que se usa al registrar se puede calcular aquí con reglas deterministas.
    Si la solicitud ya existe, el flujo termina sin gastar tokens. Si no se puede calcular
    (producto inexistente, datos contradictorios o sin reposición), se deja seguir a A01,
    que es quien maneja esos casos. La verificación final antes de registrar se mantiene.
    """
    def _sigue(motivo: str) -> dict:
        return {
            "ya_procesada": False,
            "errores": [],
            "trazas": [{"nodo": "detectar_duplicado", "resultado": "sin_duplicado", "motivo": motivo}],
            "alertas": [],
        }

    registro = consultar_inventario.invoke({"id_producto": estado["id_producto"], "sede": estado["sede"]})
    if "error" in registro:
        return _sigue("producto no encontrado: lo maneja A01")
    if (registro["cantidad_disponible"] != estado["cantidad_disponible"]
            or registro["stock_minimo"] != estado["stock_minimo"]):
        return _sigue("datos contradictorios: lo maneja A01")
    if not determinar_reposicion(registro["cantidad_disponible"], registro["stock_minimo"]):
        return _sigue("no requiere reposición")

    cantidad_final = estado.get("cantidad_solicitada") or calcular_cantidad_sugerida(
        registro["cantidad_disponible"], registro["stock_minimo"]
    )
    clave = calcular_clave(
        id_producto=estado["id_producto"],
        sede=estado["sede"],
        cantidad_solicitada=cantidad_final,
        fecha_solicitud=estado["fecha_solicitud"],
        cantidad_disponible=estado["cantidad_disponible"],
    )
    ya_procesada, existente = verificar_idempotencia(clave, _RUTA_SOLICITUDES)
    if not ya_procesada:
        return _sigue("clave nueva")

    return {
        "ya_procesada": True,
        "solicitud_existente": existente,
        "solicitud_registrada": existente,
        "clave_idempotencia": clave,
        "codigo_solicitud": generar_codigo(clave, estado["fecha_solicitud"]),
        "requiere_reposicion": True,
        "prioridad": existente.get("prioridad"),
        "cantidad_sugerida": existente.get("cantidad_solicitada"),
        "errores": [],
        "trazas": [{"nodo": "detectar_duplicado", "resultado": "YA_PROCESADA", "clave": clave[:8] + "..."}],
        "alertas": [],
    }


def nodo_decidir_hitl(estado: EstadoAbastecimiento) -> dict:
    """Llama a la compuerta HITL y actualiza decision_hitl en el estado."""
    decision = decidir_hitl(dict(estado))
    return {
        "decision_hitl": decision,
        "errores": [],
        "trazas": [{"nodo": "decidir_hitl", "resultado": decision}],
        "alertas": [],
    }


def nodo_verificar_idempotencia(estado: EstadoAbastecimiento) -> dict:
    """
    Calcula la clave SHA-256 JUSTO ANTES de registrar.
    La cantidad se obtiene de la propuesta de A02 (ya incorpora cantidad_final).
    """
    propuesta = estado.get("propuesta", {})
    cantidad_final = propuesta.get("cantidad_solicitada", 0) if propuesta else 0

    clave = calcular_clave(
        id_producto=estado["id_producto"],
        sede=estado["sede"],
        cantidad_solicitada=cantidad_final,
        fecha_solicitud=estado["fecha_solicitud"],
        cantidad_disponible=estado["cantidad_disponible"],
    )
    codigo = generar_codigo(clave, estado["fecha_solicitud"])

    ya_procesada, solicitud_existente = verificar_idempotencia(clave, _RUTA_SOLICITUDES)

    return {
        "clave_idempotencia": clave,
        "codigo_solicitud": codigo,
        "ya_procesada": ya_procesada,
        "solicitud_existente": solicitud_existente,
        "errores": [],
        "trazas": [{
            "nodo": "verificar_idempotencia",
            "clave": clave[:8] + "...",
            "ya_procesada": ya_procesada,
        }],
        "alertas": [],
    }


def nodo_registrar_solicitud(estado: EstadoAbastecimiento) -> dict:
    """
    Registra la solicitud o devuelve la existente si ya fue procesada.
    """
    if estado.get("ya_procesada"):
        return {
            "solicitud_registrada": estado.get("solicitud_existente"),
            "errores": [],
            "trazas": [{"nodo": "registrar_solicitud", "resultado": "YA_PROCESADA"}],
            "alertas": [],
        }

    ahora = datetime.now(timezone.utc).isoformat()
    propuesta = estado.get("propuesta", {})

    nueva_solicitud = {
        "codigo_solicitud": estado.get("codigo_solicitud"),
        "clave_idempotencia": estado.get("clave_idempotencia"),
        "estado_solicitud": "PENDIENTE_COTIZACION",
        "fecha_registro": ahora,
        "id_producto": estado["id_producto"],
        "nombre_producto": estado["nombre_producto"],
        "sede": estado["sede"],
        "responsable": estado["responsable"],
        "fecha_solicitud": estado["fecha_solicitud"],
        "cantidad_disponible": estado["cantidad_disponible"],
        "stock_minimo": estado["stock_minimo"],
        "prioridad": estado.get("prioridad"),
        "cantidad_solicitada": propuesta.get("cantidad_solicitada") if propuesta else None,
        "tipo_solicitud": propuesta.get("tipo_solicitud", "Reposición") if propuesta else "Reposición",
        "observaciones": propuesta.get("observaciones", "") if propuesta else "",
        "analisis_inventario": estado.get("analisis_inventario"),
        "observaciones_validador": estado.get("observaciones_validador", []),
    }

    try:
        registrar_solicitud(nueva_solicitud, _RUTA_SOLICITUDES)
    except Exception as exc:
        mensaje = f"{type(exc).__name__}: {exc}"
        return {
            "estado_proceso": "error_sistema",
            "mensaje_error": mensaje,
            "errores": [{"nodo": "registrar_solicitud", "mensaje": mensaje}],
            "trazas": [{"nodo": "registrar_solicitud", "resultado": "error_sistema"}],
            "alertas": [],
        }

    return {
        "solicitud_registrada": nueva_solicitud,
        "errores": [],
        "trazas": [{"nodo": "registrar_solicitud", "resultado": "PENDIENTE_COTIZACION"}],
        "alertas": [],
    }


def nodo_encolar_revision(estado: EstadoAbastecimiento) -> dict:
    """Encola la solicitud para revisión humana (asistente administrativa)."""
    ahora = datetime.now(timezone.utc).isoformat()
    item = {
        "momento": ahora,
        "tipo": "revision_humana",
        "id_producto": estado["id_producto"],
        "nombre_producto": estado["nombre_producto"],
        "sede": estado["sede"],
        "responsable": estado["responsable"],
        "prioridad": estado.get("prioridad"),
        "propuesta": estado.get("propuesta"),
        "resultado_validacion": estado.get("resultado_validacion"),
        "observaciones_validador": estado.get("observaciones_validador", []),
        "errores": estado.get("errores", []),
    }

    try:
        encolar_revision(item, _RUTA_COLA_REVISION)
    except Exception as exc:
        return {
            "errores": [{"nodo": "encolar_revision", "mensaje": str(exc)}],
            "trazas": [{"nodo": "encolar_revision", "resultado": "error"}],
            "alertas": [],
        }

    return {
        "errores": [],
        "trazas": [{"nodo": "encolar_revision", "resultado": "encolado"}],
        "alertas": [],
    }


def nodo_escalar_alerta(estado: EstadoAbastecimiento) -> dict:
    """Genera una alerta a la gerente cuando hay datos contradictorios o error de sistema."""
    ahora = datetime.now(timezone.utc).isoformat()
    alerta = {
        "momento": ahora,
        "tipo": "escalamiento",
        "id_producto": estado.get("id_producto"),
        "nombre_producto": estado.get("nombre_producto"),
        "sede": estado.get("sede"),
        "estado_proceso": estado.get("estado_proceso"),
        "mensaje_error": estado.get("mensaje_error"),
        "errores": estado.get("errores", []),
    }

    try:
        registrar_alerta(alerta, _RUTA_ALERTAS)
    except Exception as exc:
        return {
            "errores": [{"nodo": "escalar_alerta", "mensaje": str(exc)}],
            "trazas": [{"nodo": "escalar_alerta", "resultado": "error"}],
            "alertas": [alerta],
        }

    return {
        "errores": [],
        "trazas": [{"nodo": "escalar_alerta", "resultado": "alerta_registrada"}],
        "alertas": [alerta],
    }


_CLASE_POR_ESTADO = {
    "error_datos": ClaseError.DATOS,
    "error_transitorio": ClaseError.TRANSITORIO,
    "error_sistema": ClaseError.SISTEMA,
}


def nodo_fin_error(estado: EstadoAbastecimiento) -> dict:
    """Nodo terminal de error: registra en cola_errores y genera alerta."""
    ahora = datetime.now(timezone.utc).isoformat()
    mensaje = estado.get("mensaje_error", "Error desconocido")
    errores_previos = estado.get("errores", [])

    # La clase real del error sale del estado_proceso; si no se reconoce, se trata como sistema
    clase = _CLASE_POR_ESTADO.get(estado.get("estado_proceso"), ClaseError.SISTEMA)

    # Registrar en cola de errores
    error = ErrorProceso(
        nodo="fin_error",
        clase_error=clase,
        mensaje=mensaje,
        carga_original={
            "id_producto": estado.get("id_producto"),
            "sede": estado.get("sede"),
            "estado_proceso": estado.get("estado_proceso"),
        },
    )
    try:
        registrar_error(error, _RUTA_COLA_ERRORES)
    except Exception:
        pass

    # Generar alerta
    alerta = {
        "momento": ahora,
        "tipo": "error_proceso",
        "clase_error": clase.value,
        "estado_proceso": estado.get("estado_proceso"),
        "mensaje": mensaje,
        "errores": errores_previos,
    }
    try:
        registrar_alerta(alerta, _RUTA_ALERTAS)
    except Exception:
        pass

    return {
        "errores": [],
        "trazas": [{"nodo": "fin_error", "resultado": "error_registrado"}],
        "alertas": [alerta],
    }


# ---------------------------------------------------------------------------
# Funciones de enrutamiento (routing)
# ---------------------------------------------------------------------------

def _ruta_tras_validacion(estado: EstadoAbastecimiento) -> str:
    """Dirige al siguiente nodo según si el contrato fue válido o no."""
    if estado.get("estado_proceso") == "ok":
        return "ok"
    return "error"


def _ruta_tras_duplicado(estado: EstadoAbastecimiento) -> str:
    """Si la solicitud ya fue registrada, termina sin llamar a los agentes."""
    return "duplicado" if estado.get("ya_procesada") else "nuevo"


def _ruta_tras_a01(estado: EstadoAbastecimiento) -> str:
    """Tras A01: los datos contradictorios van directo a la compuerta HITL (ESCALAR)."""
    if estado.get("datos_contradictorios"):
        return "contradictorio"
    return _ruta_tras_agente(estado)


def _ruta_tras_agente(estado: EstadoAbastecimiento) -> str:
    """Dirige al siguiente nodo según si el agente tuvo éxito o error."""
    ep = estado.get("estado_proceso", "ok")
    if ep in ("error_datos", "error_sistema", "error_transitorio"):
        return "error"
    return "ok"


def _ruta_hitl(estado: EstadoAbastecimiento) -> str:
    """Dirige según la decisión de la compuerta HITL."""
    return estado.get("decision_hitl", "REVISION_HUMANA")


# ---------------------------------------------------------------------------
# Construcción y compilación del grafo
# ---------------------------------------------------------------------------

def _construir_grafo() -> StateGraph:
    """Construye y retorna el StateGraph compilado."""
    grafo = StateGraph(EstadoAbastecimiento)

    # Agregar todos los nodos
    grafo.add_node("nodo_validar_contrato", nodo_validar_contrato)
    grafo.add_node("nodo_detectar_duplicado", nodo_detectar_duplicado)
    grafo.add_node("nodo_a01_inventario", nodo_a01_inventario)
    grafo.add_node("nodo_a02_abastecimiento", nodo_a02_abastecimiento)
    grafo.add_node("nodo_a03_validador", nodo_a03_validador)
    grafo.add_node("nodo_decidir_hitl", nodo_decidir_hitl)
    grafo.add_node("nodo_verificar_idempotencia", nodo_verificar_idempotencia)
    grafo.add_node("nodo_registrar_solicitud", nodo_registrar_solicitud)
    grafo.add_node("nodo_encolar_revision", nodo_encolar_revision)
    grafo.add_node("nodo_escalar_alerta", nodo_escalar_alerta)
    grafo.add_node("nodo_fin_error", nodo_fin_error)

    # Aristas desde START
    grafo.add_edge(START, "nodo_validar_contrato")

    # Tras validar contrato
    grafo.add_conditional_edges(
        "nodo_validar_contrato",
        _ruta_tras_validacion,
        {"ok": "nodo_detectar_duplicado", "error": "nodo_fin_error"},
    )

    # Verificación temprana de duplicados (sin LLM)
    grafo.add_conditional_edges(
        "nodo_detectar_duplicado",
        _ruta_tras_duplicado,
        {"duplicado": END, "nuevo": "nodo_a01_inventario"},
    )

    # Tras A01
    grafo.add_conditional_edges(
        "nodo_a01_inventario",
        _ruta_tras_a01,
        {
            "ok": "nodo_a02_abastecimiento",
            "contradictorio": "nodo_decidir_hitl",
            "error": "nodo_fin_error",
        },
    )

    # Tras A02
    grafo.add_conditional_edges(
        "nodo_a02_abastecimiento",
        _ruta_tras_agente,
        {"ok": "nodo_a03_validador", "error": "nodo_fin_error"},
    )

    # Tras A03
    grafo.add_conditional_edges(
        "nodo_a03_validador",
        _ruta_tras_agente,
        {"ok": "nodo_decidir_hitl", "error": "nodo_fin_error"},
    )

    # Compuerta HITL
    grafo.add_conditional_edges(
        "nodo_decidir_hitl",
        _ruta_hitl,
        {
            "AUTO_BORRADOR": "nodo_verificar_idempotencia",
            "REVISION_HUMANA": "nodo_encolar_revision",
            "ESCALAR": "nodo_escalar_alerta",
            "NO_REQUIERE": END,
        },
    )

    # Tras verificar idempotencia → registrar
    grafo.add_edge("nodo_verificar_idempotencia", "nodo_registrar_solicitud")
    grafo.add_edge("nodo_registrar_solicitud", END)
    grafo.add_edge("nodo_encolar_revision", END)
    grafo.add_edge("nodo_escalar_alerta", END)
    grafo.add_edge("nodo_fin_error", END)

    return grafo.compile()


# Instancia compilada del grafo (singleton de módulo)
_grafo_compilado = _construir_grafo()


def construir_estado_inicial(entrada: dict) -> EstadoAbastecimiento:
    """Arma el estado inicial del grafo a partir de los 8 campos del contrato de entrada."""
    return {
        # Campos de entrada
        "id_producto": entrada.get("id_producto", 0),
        "nombre_producto": entrada.get("nombre_producto", ""),
        "cantidad_disponible": entrada.get("cantidad_disponible", 0),
        "stock_minimo": entrada.get("stock_minimo", 0),
        "cantidad_solicitada": entrada.get("cantidad_solicitada"),
        "sede": entrada.get("sede", ""),
        "fecha_solicitud": entrada.get("fecha_solicitud", ""),
        "responsable": entrada.get("responsable", ""),

        # Control de flujo inicial
        "estado_proceso": "ok",
        "mensaje_error": None,

        # A01
        "datos_contradictorios": None,
        "requiere_reposicion": None,
        "prioridad": None,
        "cantidad_sugerida": None,
        "analisis_inventario": None,

        # A02
        "propuesta": None,

        # A03
        "resultado_validacion": None,
        "observaciones_validador": None,

        # HITL
        "decision_hitl": None,

        # Idempotencia
        "clave_idempotencia": None,
        "codigo_solicitud": None,
        "ya_procesada": None,
        "solicitud_existente": None,

        # Resultado
        "solicitud_registrada": None,

        # Acumuladores
        "errores": [],
        "trazas": [],
        "alertas": [],
    }


def ejecutar_solicitud(entrada: dict) -> dict:
    """
    Función pública: ejecuta el flujo completo dado un dict de entrada.

    Args:
        entrada: dict con los 8 campos del contrato de entrada.

    Returns:
        El estado final del grafo como dict.
    """
    resultado = _grafo_compilado.invoke(
        construir_estado_inicial(entrada),
        config={"run_name": "Orquestador de Abastecimiento (LangGraph)"},
    )
    return dict(resultado)
