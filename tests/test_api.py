"""
Pruebas de la API FastAPI y la interfaz web.
Usa TestClient (sin servidor real) y LLMFalso: NUNCA se llama al LLM real.
Las rutas de persistencia apuntan a archivos temporales (fixture rutas_temporales).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from botica.api.main import aplicacion
from botica.estado.esquemas import PropuestaAbastecimiento, RedaccionInventario, SalidaValidador

_DATOS_REALES = Path(__file__).parent.parent / "conocimiento" / "datos"


@pytest.fixture
def cliente() -> TestClient:
    return TestClient(aplicacion)


@pytest.fixture
def llm_configurado(monkeypatch: pytest.MonkeyPatch, llm_falso):
    """LLMFalso con respuestas para los tres agentes (validador APROBADO)."""
    llm_falso.configurar(RedaccionInventario, RedaccionInventario(analisis="Stock bajo el mínimo."))
    llm_falso.configurar(
        PropuestaAbastecimiento,
        PropuestaAbastecimiento(
            producto="Paracetamol 500 mg",
            sede="Sede Bolognesi 606",
            cantidad_solicitada=22,
            prioridad="alta",
            tipo_solicitud="Reposición",
            observaciones="Reposición por stock bajo.",
        ),
    )
    llm_falso.configurar(SalidaValidador, SalidaValidador(resultado="APROBADO", observaciones=[]))
    for modulo in ("a01_inventario", "a02_abastecimiento", "a03_validador"):
        monkeypatch.setattr(f"botica.agentes.{modulo}.crear_llm", lambda: llm_falso)
    return llm_falso


def _entrada(**cambios) -> dict:
    base = {
        "id_producto": 25,
        "nombre_producto": "Paracetamol 500 mg",
        "cantidad_disponible": 8,
        "stock_minimo": 15,
        "cantidad_solicitada": None,
        "sede": "Sede Bolognesi 606",
        "fecha_solicitud": "2026-10-17",
        "responsable": "Asistente administrativa",
    }
    return {**base, **cambios}


def _leer(ruta: Path) -> list:
    return json.loads(ruta.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Página e inventario
# ---------------------------------------------------------------------------

def test_pagina_principal_sirve_la_interfaz(cliente: TestClient) -> None:
    respuesta = cliente.get("/")
    assert respuesta.status_code == 200
    assert "text/html" in respuesta.headers["content-type"]
    assert "Botica Sophia · Sistema Inteligente de Abastecimiento" in respuesta.text
    assert "Reiniciar demo" in respuesta.text
    assert "Analizar" in respuesta.text


def test_inventario_devuelve_productos_y_sedes(cliente: TestClient) -> None:
    respuesta = cliente.get("/api/v1/inventario")
    assert respuesta.status_code == 200
    registros = respuesta.json()
    assert len(registros) == 7
    sedes_paracetamol = {r["sede"] for r in registros if r["id_producto"] == 25}
    assert sedes_paracetamol == {"Sede Bolognesi 606", "Almacén Central"}
    assert all({"id_producto", "nombre_producto", "sede", "cantidad_disponible", "stock_minimo"} <= set(r) for r in registros)


# ---------------------------------------------------------------------------
# POST /solicitud
# ---------------------------------------------------------------------------

def test_solicitud_devuelve_resultado_completo_y_traza(
    cliente: TestClient, llm_configurado, rutas_temporales: dict
) -> None:
    respuesta = cliente.post("/api/v1/solicitud", json=_entrada())
    assert respuesta.status_code == 200
    d = respuesta.json()

    assert d["requiere_reposicion"] is True
    assert d["prioridad"] == "alta"
    assert d["cantidad_sugerida"] == 22
    assert d["analisis_inventario"] == "Stock bajo el mínimo."
    assert d["propuesta"]["cantidad_solicitada"] == 22
    assert d["resultado_validacion"] == "APROBADO"
    assert d["observaciones_validador"] == []
    assert d["decision_hitl"] == "AUTO_BORRADOR"
    assert d["codigo_solicitud"].startswith("SOL-20261017-")
    assert d["ya_procesada"] is False

    nodos = [p["nodo"] for p in d["traza"]]
    assert nodos == [
        "nodo_validar_contrato",
        "nodo_detectar_duplicado",
        "nodo_a01_inventario",
        "nodo_a02_abastecimiento",
        "nodo_a03_validador",
        "nodo_decidir_hitl",
        "nodo_verificar_idempotencia",
        "nodo_registrar_solicitud",
    ]
    assert all(p["duracion_ms"] >= 0 for p in d["traza"])
    assert d["traza"][1]["resultado"] == "sin_duplicado"
    assert d["traza"][5]["resultado"] == "AUTO_BORRADOR"
    assert d["traza"][6]["resultado"] == "clave nueva"

    # La traza queda guardada (nodo, entrada, salida, duración) en el archivo temporal
    trazas = _leer(rutas_temporales["trazas"])
    assert [t["nodo"] for t in trazas] == nodos
    assert all(t["entrada"]["id_ejecucion"] == d["id_ejecucion"] for t in trazas)
    assert len(_leer(rutas_temporales["solicitudes"])) == 1


def test_solicitud_repetida_es_ya_procesada(cliente: TestClient, llm_configurado, rutas_temporales: dict) -> None:
    primera = cliente.post("/api/v1/solicitud", json=_entrada()).json()
    segunda = cliente.post("/api/v1/solicitud", json=_entrada()).json()

    assert primera["ya_procesada"] is False
    assert segunda["ya_procesada"] is True
    assert segunda["codigo_solicitud"] == primera["codigo_solicitud"]
    # El duplicado se detecta ANTES de los agentes: la segunda ejecución no llama al LLM
    assert [p["nodo"] for p in segunda["traza"]] == ["nodo_validar_contrato", "nodo_detectar_duplicado"]
    assert segunda["traza"][-1]["resultado"] == "YA_PROCESADA"
    assert len(llm_configurado.llamadas) == 3  # solo las 3 llamadas de la primera ejecución
    assert len(_leer(rutas_temporales["solicitudes"])) == 1


def test_solicitud_datos_contradictorios_escala(cliente: TestClient, llm_configurado, rutas_temporales: dict) -> None:
    """Stock editado en el formulario (20 en vez de 8) → ESCALAR, sin pasar por A02/A03."""
    d = cliente.post("/api/v1/solicitud", json=_entrada(cantidad_disponible=20)).json()

    assert d["datos_contradictorios"] is True
    assert d["decision_hitl"] == "ESCALAR"
    assert "cantidad_disponible informada=20, inventario=8" in d["mensaje_error"]
    assert [p["nodo"] for p in d["traza"]] == [
        "nodo_validar_contrato",
        "nodo_detectar_duplicado",
        "nodo_a01_inventario",
        "nodo_decidir_hitl",
        "nodo_escalar_alerta",
    ]
    assert llm_configurado.llamadas == []
    assert len(_leer(rutas_temporales["alertas"])) == 1


def test_solicitud_stock_suficiente_no_requiere(cliente: TestClient, llm_configurado) -> None:
    d = cliente.post(
        "/api/v1/solicitud",
        json=_entrada(id_producto=28, nombre_producto="Ibuprofeno 400 mg", cantidad_disponible=40),
    ).json()

    assert d["decision_hitl"] == "NO_REQUIERE"
    assert d["requiere_reposicion"] is False
    assert d["prioridad"] == "baja"
    assert d["cantidad_sugerida"] == 0
    assert d["propuesta"] is None
    assert d["codigo_solicitud"] is None


def test_solicitud_contrato_invalido_va_a_cola_de_errores(
    cliente: TestClient, llm_configurado, rutas_temporales: dict
) -> None:
    d = cliente.post("/api/v1/solicitud", json=_entrada(stock_minimo=0)).json()

    assert d["estado_proceso"] == "error_datos"
    assert d["decision_hitl"] is None
    assert [p["nodo"] for p in d["traza"]] == ["nodo_validar_contrato", "nodo_fin_error"]
    errores = _leer(rutas_temporales["cola_errores"])
    assert errores[0]["clase_error"] == "datos"


def test_solicitud_sin_campo_obligatorio_responde_422(cliente: TestClient) -> None:
    entrada = _entrada()
    del entrada["cantidad_disponible"]
    assert cliente.post("/api/v1/solicitud", json=entrada).status_code == 422


# ---------------------------------------------------------------------------
# Paneles y reinicio
# ---------------------------------------------------------------------------

def test_paneles_leen_los_archivos_de_seguimiento(
    cliente: TestClient, llm_configurado, rutas_temporales: dict
) -> None:
    vacio = cliente.get("/api/v1/paneles").json()
    assert vacio == {"solicitudes": [], "cola_revision": [], "alertas": [], "cola_errores": []}

    cliente.post("/api/v1/solicitud", json=_entrada())                          # AUTO_BORRADOR
    cliente.post("/api/v1/solicitud", json=_entrada(cantidad_disponible=20))    # ESCALAR
    cliente.post("/api/v1/solicitud", json=_entrada(stock_minimo=0))            # error de datos
    llm_configurado.configurar(
        SalidaValidador, SalidaValidador(resultado="OBSERVADO", observaciones=["Falta un dato."])
    )
    cliente.post("/api/v1/solicitud", json=_entrada(cantidad_solicitada=30))    # REVISION_HUMANA

    p = cliente.get("/api/v1/paneles").json()
    assert len(p["solicitudes"]) == 1
    assert p["solicitudes"][0]["estado_solicitud"] == "PENDIENTE_COTIZACION"
    assert len(p["cola_revision"]) == 1
    assert p["cola_revision"][0]["observaciones_validador"] == ["Falta un dato."]
    assert len(p["alertas"]) == 2  # escalamiento + alerta del error de datos
    assert len(p["cola_errores"]) == 1


def test_reiniciar_vacia_seguimiento_sin_tocar_inventario(
    cliente: TestClient, llm_configurado, rutas_temporales: dict
) -> None:
    inventario = _DATOS_REALES / "inventario.json"
    inventario_antes = inventario.read_bytes()
    reales_antes = {p.name: p.stat().st_mtime_ns for p in _DATOS_REALES.glob("*.json")}

    cliente.post("/api/v1/solicitud", json=_entrada())
    cliente.post("/api/v1/solicitud", json=_entrada(cantidad_disponible=20))
    cliente.post("/api/v1/solicitud", json=_entrada(stock_minimo=0))

    respuesta = cliente.post("/api/v1/reiniciar")
    assert respuesta.status_code == 200
    assert respuesta.json()["archivos"] == ["alertas", "cola_errores", "cola_revision", "solicitudes", "trazas"]

    for nombre in ("solicitudes", "alertas", "cola_revision", "cola_errores", "trazas"):
        assert _leer(rutas_temporales[nombre]) == [], nombre

    # El inventario sigue intacto y los archivos reales no se tocaron durante la prueba
    assert inventario.read_bytes() == inventario_antes
    assert {p.name: p.stat().st_mtime_ns for p in _DATOS_REALES.glob("*.json")} == reales_antes
    assert len(cliente.get("/api/v1/inventario").json()) == 7
