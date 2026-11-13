"""
Pruebas del Agente A01 (Inventario).
Usa monkeypatch para reemplazar crear_llm con LLMFalso.
NUNCA se llama al LLM real.
"""
from __future__ import annotations

import pytest

from botica.estado.esquemas import RedaccionInventario


@pytest.fixture
def estado_base_a01(datos_base: dict) -> dict:
    """Estado inicial mínimo compatible con el nodo A01."""
    return {
        **datos_base,
        "estado_proceso": "ok",
        "mensaje_error": None,
        "requiere_reposicion": None,
        "prioridad": None,
        "cantidad_sugerida": None,
        "analisis_inventario": None,
        "propuesta": None,
        "resultado_validacion": None,
        "observaciones_validador": None,
        "decision_hitl": None,
        "clave_idempotencia": None,
        "codigo_solicitud": None,
        "ya_procesada": None,
        "solicitud_existente": None,
        "solicitud_registrada": None,
        "errores": [],
        "trazas": [],
        "alertas": [],
    }


def test_a01_retorna_campos_correctos(
    monkeypatch: pytest.MonkeyPatch,
    llm_falso,
    estado_base_a01: dict,
) -> None:
    """A01 debe retornar requiere_reposicion, prioridad, cantidad_sugerida y analisis."""
    llm_falso.configurar(
        RedaccionInventario,
        RedaccionInventario(analisis="El Paracetamol 500 mg tiene stock crítico (8 uds, mínimo 15)."),
    )

    monkeypatch.setattr("botica.agentes.a01_inventario.crear_llm", lambda: llm_falso)

    from botica.agentes.a01_inventario import nodo_a01_inventario
    resultado = nodo_a01_inventario(estado_base_a01)

    assert resultado["requiere_reposicion"] is True
    assert resultado["prioridad"] == "alta"
    assert resultado["cantidad_sugerida"] == 22
    assert "analisis_inventario" in resultado
    assert resultado["estado_proceso"] == "ok"


def test_a01_retorna_no_requiere_para_ibuprofeno(
    monkeypatch: pytest.MonkeyPatch,
    llm_falso,
    datos_base: dict,
) -> None:
    """Ibuprofeno con stock suficiente → requiere_reposicion=False."""
    estado = {
        **datos_base,
        "id_producto": 28,
        "nombre_producto": "Ibuprofeno 400 mg",
        "cantidad_disponible": 40,
        "stock_minimo": 15,
        "estado_proceso": "ok",
        "mensaje_error": None,
        "requiere_reposicion": None,
        "prioridad": None,
        "cantidad_sugerida": None,
        "analisis_inventario": None,
        "propuesta": None,
        "resultado_validacion": None,
        "observaciones_validador": None,
        "decision_hitl": None,
        "clave_idempotencia": None,
        "codigo_solicitud": None,
        "ya_procesada": None,
        "solicitud_existente": None,
        "solicitud_registrada": None,
        "errores": [],
        "trazas": [],
        "alertas": [],
    }

    llm_falso.configurar(
        RedaccionInventario,
        RedaccionInventario(analisis="El Ibuprofeno 400 mg tiene stock suficiente (40 uds, mínimo 15)."),
    )
    monkeypatch.setattr("botica.agentes.a01_inventario.crear_llm", lambda: llm_falso)

    from botica.agentes.a01_inventario import nodo_a01_inventario
    resultado = nodo_a01_inventario(estado)

    assert resultado["requiere_reposicion"] is False
    assert resultado["prioridad"] == "baja"
    assert resultado["cantidad_sugerida"] == 0


def test_a01_producto_inexistente_retorna_error(
    monkeypatch: pytest.MonkeyPatch,
    llm_falso,
    datos_base: dict,
) -> None:
    """Producto con id inexistente en el inventario → error_datos."""
    estado = {
        **datos_base,
        "id_producto": 999,
        "nombre_producto": "Producto Inexistente",
        "estado_proceso": "ok",
        "mensaje_error": None,
        "requiere_reposicion": None,
        "prioridad": None,
        "cantidad_sugerida": None,
        "analisis_inventario": None,
        "propuesta": None,
        "resultado_validacion": None,
        "observaciones_validador": None,
        "decision_hitl": None,
        "clave_idempotencia": None,
        "codigo_solicitud": None,
        "ya_procesada": None,
        "solicitud_existente": None,
        "solicitud_registrada": None,
        "errores": [],
        "trazas": [],
        "alertas": [],
    }

    # El LLM no debería ser llamado para un producto inexistente
    monkeypatch.setattr("botica.agentes.a01_inventario.crear_llm", lambda: llm_falso)

    from botica.agentes.a01_inventario import nodo_a01_inventario
    resultado = nodo_a01_inventario(estado)

    assert resultado["estado_proceso"] == "error_datos"
    assert len(resultado["errores"]) > 0


def test_a01_acumula_trazas(
    monkeypatch: pytest.MonkeyPatch,
    llm_falso,
    estado_base_a01: dict,
) -> None:
    """A01 debe incluir al menos una entrada en trazas."""
    llm_falso.configurar(RedaccionInventario, RedaccionInventario(analisis="Análisis de prueba."))
    monkeypatch.setattr("botica.agentes.a01_inventario.crear_llm", lambda: llm_falso)

    from botica.agentes.a01_inventario import nodo_a01_inventario
    resultado = nodo_a01_inventario(estado_base_a01)

    assert "trazas" in resultado
    assert len(resultado["trazas"]) > 0
    assert resultado["trazas"][0]["nodo"] == "a01_inventario"


# ---------------------------------------------------------------------------
# Corrección 1: requiere_reposicion, prioridad y cantidad_sugerida salen de las reglas
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("id_producto,nombre,disponible,minimo,requiere,prioridad,sugerida", [
    (25, "Paracetamol 500 mg", 8, 15, True, "alta", 22),
    (28, "Ibuprofeno 400 mg", 40, 15, False, "baja", 0),
    (31, "Amoxicilina 500 mg", 0, 20, True, "alta", 40),
    (34, "Omeprazol 20 mg", 12, 12, True, "media", 12),
])
def test_a01_valores_salen_de_las_reglas(
    monkeypatch: pytest.MonkeyPatch,
    llm_falso,
    estado_base_a01: dict,
    id_producto: int,
    nombre: str,
    disponible: int,
    minimo: int,
    requiere: bool,
    prioridad: str,
    sugerida: int,
) -> None:
    """Los tres valores de decisión son los de botica/reglas/stock.py para cada caso de prueba."""
    estado = {
        **estado_base_a01,
        "id_producto": id_producto,
        "nombre_producto": nombre,
        "cantidad_disponible": disponible,
        "stock_minimo": minimo,
    }
    llm_falso.configurar(RedaccionInventario, RedaccionInventario(analisis="Análisis."))
    monkeypatch.setattr("botica.agentes.a01_inventario.crear_llm", lambda: llm_falso)

    from botica.agentes.a01_inventario import nodo_a01_inventario
    resultado = nodo_a01_inventario(estado)

    assert resultado["requiere_reposicion"] is requiere
    assert resultado["prioridad"] == prioridad
    assert resultado["cantidad_sugerida"] == sugerida
    assert resultado["datos_contradictorios"] is False


def test_a01_llm_solo_redacta_el_analisis(
    monkeypatch: pytest.MonkeyPatch,
    llm_falso,
    estado_base_a01: dict,
) -> None:
    """
    El LLM solo se usa con el esquema RedaccionInventario (solo analisis).
    Si A01 pidiera SalidaInventario al LLM, LLMFalso lanzaría error porque no está configurado.
    """
    llm_falso.configurar(RedaccionInventario, RedaccionInventario(analisis="Texto del LLM."))
    monkeypatch.setattr("botica.agentes.a01_inventario.crear_llm", lambda: llm_falso)

    from botica.agentes.a01_inventario import nodo_a01_inventario
    resultado = nodo_a01_inventario(estado_base_a01)

    assert resultado["estado_proceso"] == "ok"
    assert resultado["analisis_inventario"] == "Texto del LLM."
    assert resultado["cantidad_sugerida"] == 22
    assert len(llm_falso.llamadas) == 1


# ---------------------------------------------------------------------------
# Corrección 2: stock informado distinto del inventario → datos contradictorios
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("campo,valor,texto", [
    ("cantidad_disponible", 20, "cantidad_disponible informada=20, inventario=8"),
    ("stock_minimo", 10, "stock_minimo informado=10, inventario=15"),
])
def test_a01_marca_datos_contradictorios(
    monkeypatch: pytest.MonkeyPatch,
    llm_falso,
    estado_base_a01: dict,
    campo: str,
    valor: int,
    texto: str,
) -> None:
    """Si el stock informado no coincide con el inventario real, A01 marca datos contradictorios."""
    estado = {**estado_base_a01, campo: valor}
    monkeypatch.setattr("botica.agentes.a01_inventario.crear_llm", lambda: llm_falso)

    from botica.agentes.a01_inventario import nodo_a01_inventario
    resultado = nodo_a01_inventario(estado)

    assert resultado["datos_contradictorios"] is True
    assert resultado["estado_proceso"] == "datos_contradictorios"
    assert texto in resultado["mensaje_error"]
    # No se gasta cupo del LLM en un caso que se va a escalar
    assert llm_falso.llamadas == []


# ---------------------------------------------------------------------------
# Corrección 5: los errores se escriben en archivos temporales, no en los reales
# ---------------------------------------------------------------------------

def test_a01_error_va_a_cola_temporal_y_no_a_la_real(
    monkeypatch: pytest.MonkeyPatch,
    llm_falso,
    estado_base_a01: dict,
    rutas_temporales: dict,
) -> None:
    """El producto inexistente se registra en la cola de errores temporal; la real no cambia."""
    import json
    from pathlib import Path

    ruta_real = Path(__file__).parent.parent / "conocimiento" / "datos" / "cola_errores.json"
    contenido_real_antes = ruta_real.read_text(encoding="utf-8")

    estado = {**estado_base_a01, "id_producto": 999, "nombre_producto": "Producto Inexistente"}
    monkeypatch.setattr("botica.agentes.a01_inventario.crear_llm", lambda: llm_falso)

    from botica.agentes.a01_inventario import nodo_a01_inventario
    nodo_a01_inventario(estado)

    cola_temporal = json.loads(rutas_temporales["cola_errores"].read_text(encoding="utf-8"))
    assert len(cola_temporal) == 1
    assert cola_temporal[0]["clase_error"] == "datos"
    assert ruta_real.read_text(encoding="utf-8") == contenido_real_antes
