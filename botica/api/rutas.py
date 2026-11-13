"""
Rutas de la API FastAPI.
Define los endpoints del sistema multiagente de abastecimiento.
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException

import botica.orquestador.grafo as grafo_mod
from botica.api.modelos_api import (
    EntradaSolicitudAPI,
    PanelesAPI,
    PasoTraza,
    RespuestaSolicitudAPI,
)
from botica.herramientas.consultar_inventario import _RUTA_INVENTARIO
from botica.trazabilidad.trazador import registrar_traza

enrutador = APIRouter()

_RAIZ = Path(__file__).parent.parent.parent
_RUTA_TRAZAS = str(_RAIZ / "conocimiento" / "datos" / "trazas.json")


def _rutas_seguimiento() -> dict[str, str]:
    """
    Rutas de los archivos que se muestran en los paneles y que vacía "Reiniciar demo".
    Se leen del módulo del grafo en cada llamada para que los tests puedan redirigirlas.
    No incluye el inventario.
    """
    return {
        "solicitudes": grafo_mod._RUTA_SOLICITUDES,
        "cola_revision": grafo_mod._RUTA_COLA_REVISION,
        "alertas": grafo_mod._RUTA_ALERTAS,
        "cola_errores": grafo_mod._RUTA_COLA_ERRORES,
        "trazas": _RUTA_TRAZAS,
    }


def _leer_lista(ruta: str | Path) -> list:
    """Lee un archivo JSON de lista; si no existe o está vacío devuelve []."""
    ruta = Path(ruta)
    if not ruta.exists():
        return []
    contenido = ruta.read_text(encoding="utf-8").strip()
    return json.loads(contenido) if contenido else []


def _resultado_paso(nodo: str, actualizacion: dict) -> str:
    """Resume en un texto el resultado de un nodo a partir de lo que escribió en el estado."""
    trazas = actualizacion.get("trazas") or []
    if trazas and "resultado" in trazas[0]:
        return str(trazas[0]["resultado"])
    if "ya_procesada" in actualizacion:
        return "YA_PROCESADA" if actualizacion["ya_procesada"] else "clave nueva"
    return "ok"


def _ejecutar_con_traza(entrada: dict) -> tuple[dict, list[PasoTraza]]:
    """
    Ejecuta el grafo compilado nodo por nodo (stream) y mide la duración de cada uno.
    No cambia la lógica del grafo: es el mismo grafo que usa ejecutar_solicitud.
    """
    estado_final: dict = {}
    pasos: list[tuple[str, dict, float]] = []
    marca = time.perf_counter()

    for modo, dato in grafo_mod._grafo_compilado.stream(
        grafo_mod.construir_estado_inicial(entrada),
        stream_mode=["updates", "values"],
        config={"run_name": "Orquestador de Abastecimiento (LangGraph)"},
    ):
        if modo == "updates":
            ahora = time.perf_counter()
            for nodo, actualizacion in dato.items():
                pasos.append((nodo, actualizacion or {}, (ahora - marca) * 1000))
            marca = ahora
        else:
            estado_final = dict(dato)

    id_ejecucion = str(uuid.uuid4())
    traza = [
        PasoTraza(nodo=nodo, resultado=_resultado_paso(nodo, act), duracion_ms=round(ms, 2))
        for nodo, act, ms in pasos
    ]

    # Trazabilidad: cada nodo queda guardado con su entrada, salida y duración
    for nodo, actualizacion, ms in pasos:
        registrar_traza(
            nodo=nodo,
            entrada={"id_ejecucion": id_ejecucion, "solicitud": entrada},
            salida=json.loads(json.dumps(actualizacion, ensure_ascii=False, default=str)),
            duracion_ms=ms,
            archivo=_RUTA_TRAZAS,
        )

    estado_final["id_ejecucion"] = id_ejecucion
    return estado_final, traza


@enrutador.post(
    "/solicitud",
    response_model=RespuestaSolicitudAPI,
    summary="Genera una solicitud de abastecimiento",
    description=(
        "Recibe los datos del producto con stock bajo y ejecuta el flujo multiagente "
        "completo: validación, análisis de inventario, propuesta de abastecimiento, "
        "validación y compuerta HITL."
    ),
)
def crear_solicitud(entrada: EntradaSolicitudAPI) -> RespuestaSolicitudAPI:
    """Endpoint principal: ejecuta el grafo de abastecimiento y devuelve su traza."""
    try:
        resultado, traza = _ejecutar_con_traza(entrada.model_dump())
        return RespuestaSolicitudAPI(
            id_ejecucion=resultado.get("id_ejecucion"),
            estado_proceso=resultado.get("estado_proceso", "ok"),
            datos_contradictorios=resultado.get("datos_contradictorios"),
            requiere_reposicion=resultado.get("requiere_reposicion"),
            prioridad=resultado.get("prioridad"),
            cantidad_sugerida=resultado.get("cantidad_sugerida"),
            analisis_inventario=resultado.get("analisis_inventario"),
            propuesta=resultado.get("propuesta"),
            resultado_validacion=resultado.get("resultado_validacion"),
            observaciones_validador=resultado.get("observaciones_validador"),
            decision_hitl=resultado.get("decision_hitl"),
            codigo_solicitud=resultado.get("codigo_solicitud"),
            ya_procesada=resultado.get("ya_procesada"),
            solicitud_registrada=resultado.get("solicitud_registrada"),
            mensaje_error=resultado.get("mensaje_error"),
            errores=resultado.get("errores", []),
            trazas=resultado.get("trazas", []),
            alertas=resultado.get("alertas", []),
            traza=traza,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@enrutador.get(
    "/inventario",
    summary="Lista el inventario (productos y sedes) para el formulario",
)
def listar_inventario() -> list[dict]:
    """Devuelve los registros de conocimiento/datos/inventario.json (solo lectura)."""
    return _leer_lista(_RUTA_INVENTARIO)


@enrutador.get(
    "/paneles",
    response_model=PanelesAPI,
    summary="Solicitudes, cola de revisión, alertas y cola de errores",
)
def ver_paneles() -> PanelesAPI:
    """Lee los archivos de seguimiento para los paneles de la interfaz."""
    rutas = _rutas_seguimiento()
    return PanelesAPI(
        solicitudes=_leer_lista(rutas["solicitudes"]),
        cola_revision=_leer_lista(rutas["cola_revision"]),
        alertas=_leer_lista(rutas["alertas"]),
        cola_errores=_leer_lista(rutas["cola_errores"]),
    )


@enrutador.post(
    "/reiniciar",
    summary="Reinicia la demo",
    description="Vacía solicitudes, alertas, cola de revisión, cola de errores y trazas. No toca el inventario.",
)
def reiniciar_demo() -> dict:
    """Deja como listas vacías los archivos de seguimiento (el inventario no se modifica)."""
    rutas = _rutas_seguimiento()
    for ruta in rutas.values():
        destino = Path(ruta)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text("[]\n", encoding="utf-8")
    return {"estado": "reiniciado", "archivos": sorted(rutas)}


@enrutador.get(
    "/salud",
    summary="Comprueba que la API está en línea",
)
async def verificar_salud() -> dict:
    """Endpoint de salud para verificar que el servicio responde."""
    return {"estado": "activo", "sistema": "BoticaSophiaAgentic"}
