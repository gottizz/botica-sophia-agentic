"""
Esquemas Pydantic y TypedDict para el estado compartido del grafo LangGraph.
Define los modelos de entrada/salida de cada agente y el estado global.
"""
from __future__ import annotations

import operator
from typing import Optional, Annotated

from pydantic import BaseModel
from typing_extensions import TypedDict


class SolicitudEntrada(BaseModel):
    """Contrato de entrada: los 8 campos que debe proveer el solicitante."""

    id_producto: int
    nombre_producto: str
    cantidad_disponible: int
    stock_minimo: int
    cantidad_solicitada: Optional[int] = None
    sede: str
    fecha_solicitud: str
    responsable: str


class RedaccionInventario(BaseModel):
    """Salida estructurada del LLM en A01: solo la redacción del análisis."""

    analisis: str  # narrativa del análisis


class SalidaInventario(BaseModel):
    """
    Salida del Agente A01 (Inventario).
    requiere_reposicion, prioridad y cantidad_sugerida vienen de botica/reglas/stock.py;
    solo analisis lo redacta el LLM.
    """

    requiere_reposicion: bool
    prioridad: str  # "alta" | "media" | "baja"
    cantidad_sugerida: int
    analisis: str  # narrativa del análisis


class PropuestaAbastecimiento(BaseModel):
    """Salida estructurada del Agente A02 (Abastecimiento)."""

    producto: str
    sede: str
    cantidad_solicitada: int
    prioridad: str
    tipo_solicitud: str  # siempre "Reposición"
    observaciones: str


class SalidaValidador(BaseModel):
    """Salida estructurada del Agente A03 (Validador)."""

    resultado: str  # "APROBADO" | "OBSERVADO"
    observaciones: list[str]


class EstadoAbastecimiento(TypedDict):
    """Estado compartido del grafo LangGraph. Todos los nodos leen y escriben aquí."""

    # --- Entrada ---
    id_producto: int
    nombre_producto: str
    cantidad_disponible: int
    stock_minimo: int
    cantidad_solicitada: Optional[int]
    sede: str
    fecha_solicitud: str
    responsable: str

    # --- Control de flujo ---
    # "ok" | "datos_contradictorios" | "error_datos" | "error_sistema" | "error_transitorio"
    estado_proceso: str
    mensaje_error: Optional[str]

    # --- A01 ---
    datos_contradictorios: Optional[bool]  # stock informado ≠ inventario real → ESCALAR
    requiere_reposicion: Optional[bool]
    prioridad: Optional[str]
    cantidad_sugerida: Optional[int]
    analisis_inventario: Optional[str]

    # --- A02 ---
    propuesta: Optional[dict]

    # --- A03 ---
    resultado_validacion: Optional[str]
    observaciones_validador: Optional[list]

    # --- HITL ---
    decision_hitl: Optional[str]

    # --- Idempotencia ---
    clave_idempotencia: Optional[str]
    codigo_solicitud: Optional[str]
    ya_procesada: Optional[bool]
    solicitud_existente: Optional[dict]

    # --- Resultado ---
    solicitud_registrada: Optional[dict]

    # --- Acumuladores (LangGraph usa operator.add para listas) ---
    errores: Annotated[list, operator.add]
    trazas: Annotated[list, operator.add]
    alertas: Annotated[list, operator.add]
