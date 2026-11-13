"""
Modelos Pydantic para la API FastAPI.
Definen las estructuras de request y response de los endpoints.
"""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel


class EntradaSolicitudAPI(BaseModel):
    """Cuerpo de la petición POST /solicitud."""

    id_producto: int
    nombre_producto: str
    cantidad_disponible: int
    stock_minimo: int
    cantidad_solicitada: Optional[int] = None
    sede: str
    fecha_solicitud: str
    responsable: str


class PasoTraza(BaseModel):
    """Un nodo del grafo por el que pasó la ejecución."""

    nodo: str
    resultado: str
    duracion_ms: float


class RespuestaSolicitudAPI(BaseModel):
    """Respuesta del endpoint POST /solicitud."""

    id_ejecucion: Optional[str] = None
    estado_proceso: str
    datos_contradictorios: Optional[bool] = None
    requiere_reposicion: Optional[bool] = None
    prioridad: Optional[str] = None
    cantidad_sugerida: Optional[int] = None
    analisis_inventario: Optional[str] = None
    propuesta: Optional[dict] = None
    resultado_validacion: Optional[str] = None
    observaciones_validador: Optional[list] = None
    decision_hitl: Optional[str] = None
    codigo_solicitud: Optional[str] = None
    ya_procesada: Optional[bool] = None
    solicitud_registrada: Optional[dict] = None
    mensaje_error: Optional[str] = None
    errores: list = []
    trazas: list = []
    alertas: list = []
    traza: list[PasoTraza] = []


class PanelesAPI(BaseModel):
    """Contenido de los archivos de seguimiento en conocimiento/datos/."""

    solicitudes: list = []
    cola_revision: list = []
    alertas: list = []
    cola_errores: list = []
