"""
Compuerta HITL (Human-In-The-Loop).
Decide de forma determinista si la solicitud se aprueba automáticamente,
va a revisión humana o debe escalarse.
"""
from __future__ import annotations


def decidir_hitl(estado: dict) -> str:
    """
    Evalúa el estado del proceso y devuelve la decisión HITL.

    Retorna:
        "AUTO_BORRADOR"   → datos válidos + stock bajo + validador APROBADO.
        "REVISION_HUMANA" → validador OBSERVADO o falta algún dato secundario.
        "ESCALAR"         → datos contradictorios o error de sistema/transitorio.
        "NO_REQUIERE"     → el stock no requiere reposición.
    """
    estado_proceso = estado.get("estado_proceso", "")
    requiere_reposicion = estado.get("requiere_reposicion")
    resultado_validacion = estado.get("resultado_validacion")
    decision_hitl_previa = estado.get("decision_hitl")

    # Datos contradictorios: A01 detectó que el stock informado no coincide con el inventario real
    if estado.get("datos_contradictorios") or estado_proceso == "datos_contradictorios":
        return "ESCALAR"

    # Si ya fue marcado como NO_REQUIERE por A02, lo respetamos
    if decision_hitl_previa == "NO_REQUIERE":
        return "NO_REQUIERE"

    # Error de sistema o transitorio → escalar
    if estado_proceso in ("error_sistema", "error_transitorio"):
        return "ESCALAR"

    # Error de datos que llegue a la compuerta → escalar
    if estado_proceso == "error_datos":
        return "ESCALAR"

    propuesta = estado.get("propuesta")

    # Condición de aprobación automática: requiere propuesta válida
    if (
        estado_proceso == "ok"
        and requiere_reposicion is True
        and resultado_validacion == "APROBADO"
        and propuesta is not None
    ):
        return "AUTO_BORRADOR"

    # Validador observó algo o no hay propuesta válida
    if resultado_validacion == "OBSERVADO":
        return "REVISION_HUMANA"

    # Falta algún dato secundario (propuesta ausente, etc.)
    if propuesta is None and requiere_reposicion is True:
        return "REVISION_HUMANA"

    # Por defecto, si no se cumple ninguna condición clara → revisión humana
    return "REVISION_HUMANA"
