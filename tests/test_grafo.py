"""
Pruebas end-to-end del grafo LangGraph completo.
Usa monkeypatch para reemplazar los nodos de agentes LLM con funciones fake.
NUNCA se llama al LLM real ni a la red.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from botica.estado.esquemas import (
    PropuestaAbastecimiento,
    SalidaInventario,
    SalidaValidador,
)


# ---------------------------------------------------------------------------
# Helpers para construir nodos fake
# ---------------------------------------------------------------------------

def _nodo_a01_fake(
    requiere: bool,
    prioridad: str,
    sugerida: int,
    analisis: str = "Análisis de prueba.",
    estado_proceso: str = "ok",
):
    """Retorna una función que simula el nodo A01 con valores fijos."""
    def _nodo(estado):
        if estado_proceso != "ok":
            return {
                "estado_proceso": estado_proceso,
                "mensaje_error": "Error simulado en A01",
                "errores": [{"nodo": "a01_inventario", "mensaje": "Error simulado"}],
                "trazas": [],
                "alertas": [],
            }
        return {
            "requiere_reposicion": requiere,
            "prioridad": prioridad,
            "cantidad_sugerida": sugerida,
            "analisis_inventario": analisis,
            "estado_proceso": "ok",
            "errores": [],
            "trazas": [{"nodo": "a01_inventario", "resultado": "ok"}],
            "alertas": [],
        }
    return _nodo


def _nodo_a02_fake(
    propuesta_dict: dict | None,
    decision_no_requiere: bool = False,
):
    """Retorna una función que simula el nodo A02 con valores fijos."""
    def _nodo(estado):
        if decision_no_requiere:
            return {
                "decision_hitl": "NO_REQUIERE",
                "estado_proceso": "ok",
                "errores": [],
                "trazas": [{"nodo": "a02_abastecimiento", "resultado": "NO_REQUIERE"}],
                "alertas": [],
            }
        return {
            "propuesta": propuesta_dict,
            "estado_proceso": "ok",
            "errores": [],
            "trazas": [{"nodo": "a02_abastecimiento", "resultado": "ok"}],
            "alertas": [],
        }
    return _nodo


def _nodo_a03_fake(resultado_validacion: str, observaciones: list[str] | None = None):
    """Retorna una función que simula el nodo A03 con valores fijos."""
    def _nodo(estado):
        if estado.get("decision_hitl") == "NO_REQUIERE":
            return {
                "errores": [],
                "trazas": [{"nodo": "a03_validador", "resultado": "omitido"}],
                "alertas": [],
            }
        return {
            "resultado_validacion": resultado_validacion,
            "observaciones_validador": observaciones or [],
            "estado_proceso": "ok",
            "errores": [],
            "trazas": [{"nodo": "a03_validador", "resultado": resultado_validacion}],
            "alertas": [],
        }
    return _nodo


def _propuesta_paracetamol(cantidad: int = 22) -> dict:
    """Propuesta estándar de Paracetamol para los tests."""
    return {
        "producto": "Paracetamol 500 mg",
        "sede": "Sede Bolognesi 606",
        "cantidad_solicitada": cantidad,
        "prioridad": "alta",
        "tipo_solicitud": "Reposición",
        "observaciones": "Reposición urgente.",
    }


def _parchear_agentes(
    monkeypatch: pytest.MonkeyPatch,
    fn_a01,
    fn_a02,
    fn_a03,
    archivo_solicitudes: str | None = None,
    archivo_alertas: str | None = None,
    archivo_cola_revision: str | None = None,
    archivo_cola_errores: str | None = None,
) -> None:
    """
    Parchea los tres nodos de agentes y las rutas de archivos en el grafo.
    """
    import botica.orquestador.grafo as grafo_mod

    monkeypatch.setattr(grafo_mod, "nodo_a01_inventario", fn_a01)
    monkeypatch.setattr(grafo_mod, "nodo_a02_abastecimiento", fn_a02)
    monkeypatch.setattr(grafo_mod, "nodo_a03_validador", fn_a03)

    if archivo_solicitudes:
        monkeypatch.setattr(grafo_mod, "_RUTA_SOLICITUDES", archivo_solicitudes)
    if archivo_alertas:
        monkeypatch.setattr(grafo_mod, "_RUTA_ALERTAS", archivo_alertas)
    if archivo_cola_revision:
        monkeypatch.setattr(grafo_mod, "_RUTA_COLA_REVISION", archivo_cola_revision)
    if archivo_cola_errores:
        monkeypatch.setattr(grafo_mod, "_RUTA_COLA_ERRORES", archivo_cola_errores)


def _ejecutar(monkeypatch, fn_a01, fn_a02, fn_a03, entrada, inventario_limpio):
    """Helper: parchea nodos, reconstruye el grafo y ejecuta."""
    import botica.orquestador.grafo as grafo_mod

    _parchear_agentes(
        monkeypatch,
        fn_a01,
        fn_a02,
        fn_a03,
        archivo_solicitudes=str(inventario_limpio["solicitudes"]),
        archivo_alertas=str(inventario_limpio["alertas"]),
        archivo_cola_revision=str(inventario_limpio["cola_revision"]),
        archivo_cola_errores=str(inventario_limpio["cola_errores"]),
    )

    # Reconstruir el grafo con los nodos parcheados
    grafo = grafo_mod._construir_grafo()

    estado_inicial = {
        **entrada,
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
    return dict(grafo.invoke(estado_inicial))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGrafoStockBajoAltaPrioridad:
    """Paracetamol (8, 15) → prioridad alta → AUTO_BORRADOR → solicitud registrada."""

    def test_flujo_completo(self, monkeypatch, datos_base, inventario_limpio):
        fn_a01 = _nodo_a01_fake(True, "alta", 22)
        fn_a02 = _nodo_a02_fake(_propuesta_paracetamol(22))
        fn_a03 = _nodo_a03_fake("APROBADO")

        resultado = _ejecutar(monkeypatch, fn_a01, fn_a02, fn_a03, datos_base, inventario_limpio)

        assert resultado["decision_hitl"] == "AUTO_BORRADOR"
        assert resultado["solicitud_registrada"] is not None
        assert resultado["solicitud_registrada"]["estado_solicitud"] == "PENDIENTE_COTIZACION"
        assert resultado["ya_procesada"] is False

    def test_codigo_solicitud_tiene_formato_correcto(self, monkeypatch, datos_base, inventario_limpio):
        fn_a01 = _nodo_a01_fake(True, "alta", 22)
        fn_a02 = _nodo_a02_fake(_propuesta_paracetamol(22))
        fn_a03 = _nodo_a03_fake("APROBADO")

        resultado = _ejecutar(monkeypatch, fn_a01, fn_a02, fn_a03, datos_base, inventario_limpio)

        codigo = resultado.get("codigo_solicitud", "")
        assert codigo.startswith("SOL-")
        partes = codigo.split("-")
        assert len(partes) == 3


class TestGrafoStockSuficiente:
    """Ibuprofeno (40, 15) → NO_REQUIERE → grafo termina sin registrar solicitud."""

    def test_no_registra_solicitud(self, monkeypatch, inventario_limpio):
        entrada = {
            "id_producto": 28,
            "nombre_producto": "Ibuprofeno 400 mg",
            "cantidad_disponible": 40,
            "stock_minimo": 15,
            "cantidad_solicitada": None,
            "sede": "Sede Bolognesi 606",
            "fecha_solicitud": "2026-01-15",
            "responsable": "Juana Pérez",
        }

        fn_a01 = _nodo_a01_fake(False, "baja", 0)
        fn_a02 = _nodo_a02_fake(None, decision_no_requiere=True)
        fn_a03 = _nodo_a03_fake("APROBADO")

        resultado = _ejecutar(monkeypatch, fn_a01, fn_a02, fn_a03, entrada, inventario_limpio)

        assert resultado["decision_hitl"] == "NO_REQUIERE"
        assert resultado.get("solicitud_registrada") is None

        # El archivo de solicitudes debe estar vacío
        solicitudes = json.loads(inventario_limpio["solicitudes"].read_text())
        assert solicitudes == []


class TestGrafoEnMinimoMediaPrioridad:
    """Omeprazol (12, 12) → prioridad media → AUTO_BORRADOR."""

    def test_prioridad_media_aprobado(self, monkeypatch, inventario_limpio):
        entrada = {
            "id_producto": 34,
            "nombre_producto": "Omeprazol 20 mg",
            "cantidad_disponible": 12,
            "stock_minimo": 12,
            "cantidad_solicitada": None,
            "sede": "Sede Bolognesi 606",
            "fecha_solicitud": "2026-01-15",
            "responsable": "Juana Pérez",
        }

        propuesta = {
            "producto": "Omeprazol 20 mg",
            "sede": "Sede Bolognesi 606",
            "cantidad_solicitada": 12,
            "prioridad": "media",
            "tipo_solicitud": "Reposición",
            "observaciones": "Stock en nivel mínimo.",
        }

        fn_a01 = _nodo_a01_fake(True, "media", 12)
        fn_a02 = _nodo_a02_fake(propuesta)
        fn_a03 = _nodo_a03_fake("APROBADO")

        resultado = _ejecutar(monkeypatch, fn_a01, fn_a02, fn_a03, entrada, inventario_limpio)

        assert resultado["decision_hitl"] == "AUTO_BORRADOR"
        assert resultado["solicitud_registrada"]["prioridad"] == "media"


class TestGrafoSinStock:
    """Amoxicilina (0, 20) → prioridad alta → AUTO_BORRADOR."""

    def test_sin_stock_registra_solicitud(self, monkeypatch, inventario_limpio):
        entrada = {
            "id_producto": 31,
            "nombre_producto": "Amoxicilina 500 mg",
            "cantidad_disponible": 0,
            "stock_minimo": 20,
            "cantidad_solicitada": None,
            "sede": "Sede Bolognesi 606",
            "fecha_solicitud": "2026-01-15",
            "responsable": "Juana Pérez",
        }

        propuesta = {
            "producto": "Amoxicilina 500 mg",
            "sede": "Sede Bolognesi 606",
            "cantidad_solicitada": 40,
            "prioridad": "alta",
            "tipo_solicitud": "Reposición",
            "observaciones": "Sin stock. Urgente.",
        }

        fn_a01 = _nodo_a01_fake(True, "alta", 40)
        fn_a02 = _nodo_a02_fake(propuesta)
        fn_a03 = _nodo_a03_fake("APROBADO")

        resultado = _ejecutar(monkeypatch, fn_a01, fn_a02, fn_a03, entrada, inventario_limpio)

        assert resultado["decision_hitl"] == "AUTO_BORRADOR"
        assert resultado["solicitud_registrada"] is not None


class TestGrafoValidadorObservado:
    """LLMFalso devuelve OBSERVADO → REVISION_HUMANA."""

    def test_observado_va_a_revision_humana(self, monkeypatch, datos_base, inventario_limpio):
        fn_a01 = _nodo_a01_fake(True, "alta", 22)
        fn_a02 = _nodo_a02_fake(_propuesta_paracetamol(22))
        fn_a03 = _nodo_a03_fake("OBSERVADO", ["Cantidad no justificada."])

        resultado = _ejecutar(monkeypatch, fn_a01, fn_a02, fn_a03, datos_base, inventario_limpio)

        assert resultado["decision_hitl"] == "REVISION_HUMANA"
        assert resultado.get("solicitud_registrada") is None

        # El ítem debe estar en la cola de revisión
        cola = json.loads(inventario_limpio["cola_revision"].read_text())
        assert len(cola) == 1
        assert cola[0]["resultado_validacion"] == "OBSERVADO"


class TestGrafoSolicitudDuplicada:
    """Mismos datos dos veces → segunda vez YA_PROCESADA."""

    def test_segunda_solicitud_es_duplicada(self, monkeypatch, datos_base, inventario_limpio):
        fn_a01 = _nodo_a01_fake(True, "alta", 22)
        fn_a02 = _nodo_a02_fake(_propuesta_paracetamol(22))
        fn_a03 = _nodo_a03_fake("APROBADO")

        # Primera solicitud
        resultado1 = _ejecutar(
            monkeypatch, fn_a01, fn_a02, fn_a03, datos_base, inventario_limpio
        )
        assert resultado1["ya_procesada"] is False
        assert resultado1["solicitud_registrada"] is not None

        # Segunda solicitud con los mismos datos
        resultado2 = _ejecutar(
            monkeypatch, fn_a01, fn_a02, fn_a03, datos_base, inventario_limpio
        )
        assert resultado2["ya_procesada"] is True
        assert resultado2["solicitud_registrada"] is not None
        assert resultado2["codigo_solicitud"] == resultado1["codigo_solicitud"]
        # Detectado al inicio: los agentes A01, A02 y A03 no se ejecutan la segunda vez
        assert [tr["nodo"] for tr in resultado2["trazas"]] == ["validar_contrato", "detectar_duplicado"]

        # Solo debe haber 1 solicitud en el archivo
        solicitudes = json.loads(inventario_limpio["solicitudes"].read_text())
        assert len(solicitudes) == 1


class TestGrafoDatosInvalidos:
    """id_producto = -1 → error_datos, no registra solicitud."""

    def test_datos_invalidos_no_registran(self, monkeypatch, inventario_limpio):
        entrada_invalida = {
            "id_producto": -1,  # Inválido
            "nombre_producto": "Paracetamol 500 mg",
            "cantidad_disponible": 8,
            "stock_minimo": 15,
            "cantidad_solicitada": None,
            "sede": "Sede Bolognesi 606",
            "fecha_solicitud": "2026-01-15",
            "responsable": "Juana Pérez",
        }

        fn_a01 = _nodo_a01_fake(True, "alta", 22)
        fn_a02 = _nodo_a02_fake(_propuesta_paracetamol(22))
        fn_a03 = _nodo_a03_fake("APROBADO")

        resultado = _ejecutar(
            monkeypatch, fn_a01, fn_a02, fn_a03, entrada_invalida, inventario_limpio
        )

        assert resultado["estado_proceso"] == "error_datos"
        assert resultado.get("solicitud_registrada") is None

        solicitudes = json.loads(inventario_limpio["solicitudes"].read_text())
        assert solicitudes == []


class TestGrafoProductoInexistente:
    """id=999 → error_datos desde A01."""

    def test_producto_inexistente_error_datos(self, monkeypatch, inventario_limpio):
        entrada = {
            "id_producto": 999,
            "nombre_producto": "Producto Fantasma",
            "cantidad_disponible": 0,
            "stock_minimo": 10,
            "cantidad_solicitada": None,
            "sede": "Sede Bolognesi 606",
            "fecha_solicitud": "2026-01-15",
            "responsable": "Juana Pérez",
        }

        # A01 fake que simula producto no encontrado
        fn_a01 = _nodo_a01_fake(True, "alta", 10, estado_proceso="error_datos")
        fn_a02 = _nodo_a02_fake(_propuesta_paracetamol(10))
        fn_a03 = _nodo_a03_fake("APROBADO")

        resultado = _ejecutar(
            monkeypatch, fn_a01, fn_a02, fn_a03, entrada, inventario_limpio
        )

        # error_datos de A01 → nodo_fin_error → no registra solicitud
        assert resultado["estado_proceso"] == "error_datos"
        assert resultado.get("solicitud_registrada") is None


class TestGrafoErrorRepositorio:
    """Simula excepción al leer inventario → cola_errores + alerta."""

    def test_error_sistema_genera_alerta(self, monkeypatch, datos_base, inventario_limpio):
        # A01 que simula error de sistema
        fn_a01 = _nodo_a01_fake(True, "alta", 22, estado_proceso="error_sistema")
        fn_a02 = _nodo_a02_fake(_propuesta_paracetamol(22))
        fn_a03 = _nodo_a03_fake("APROBADO")

        resultado = _ejecutar(
            monkeypatch, fn_a01, fn_a02, fn_a03, datos_base, inventario_limpio
        )

        assert resultado["estado_proceso"] == "error_sistema"
        assert resultado.get("solicitud_registrada") is None

        # Debe haber una alerta registrada
        alertas = json.loads(inventario_limpio["alertas"].read_text())
        assert len(alertas) >= 1


# ---------------------------------------------------------------------------
# Corrección 2: datos contradictorios → la compuerta HITL decide ESCALAR
# ---------------------------------------------------------------------------

class TestGrafoDatosContradictorios:
    """Stock informado distinto del inventario → ESCALAR con alerta a la gerente."""

    def test_stock_informado_distinto_escala(self, monkeypatch, datos_base, inventario_limpio):
        from botica.agentes.a01_inventario import nodo_a01_inventario

        entrada = {**datos_base, "cantidad_disponible": 20}  # el inventario real dice 8

        def _no_debe_ejecutarse(estado):
            raise AssertionError("A02/A03 no deben ejecutarse con datos contradictorios")

        # A01 real: detecta la contradicción sin llamar al LLM
        resultado = _ejecutar(
            monkeypatch, nodo_a01_inventario, _no_debe_ejecutarse, _no_debe_ejecutarse,
            entrada, inventario_limpio,
        )

        assert resultado["datos_contradictorios"] is True
        assert resultado["decision_hitl"] == "ESCALAR"
        assert resultado.get("solicitud_registrada") is None
        assert any(t["nodo"] == "decidir_hitl" and t["resultado"] == "ESCALAR" for t in resultado["trazas"])

        alertas = json.loads(inventario_limpio["alertas"].read_text())
        assert len(alertas) == 1
        assert alertas[0]["tipo"] == "escalamiento"
        assert "cantidad_disponible informada=20, inventario=8" in alertas[0]["mensaje_error"]

        solicitudes = json.loads(inventario_limpio["solicitudes"].read_text())
        assert solicitudes == []


# ---------------------------------------------------------------------------
# Corrección 4: nodo_fin_error registra la clase real del error
# ---------------------------------------------------------------------------

class TestGrafoClaseErrorReal:
    """La cola de errores guarda la clase real (datos/transitorio/sistema), no siempre SISTEMA."""

    def _cola_fin_error(self, inventario_limpio) -> list[dict]:
        cola = json.loads(inventario_limpio["cola_errores"].read_text())
        return [e for e in cola if e["nodo"] == "fin_error"]

    def test_contrato_invalido_registra_clase_datos(self, monkeypatch, datos_base, inventario_limpio):
        entrada = {**datos_base, "id_producto": -1}
        fn_a01 = _nodo_a01_fake(True, "alta", 22)
        fn_a02 = _nodo_a02_fake(_propuesta_paracetamol(22))
        fn_a03 = _nodo_a03_fake("APROBADO")

        _ejecutar(monkeypatch, fn_a01, fn_a02, fn_a03, entrada, inventario_limpio)

        cola = self._cola_fin_error(inventario_limpio)
        assert len(cola) == 1
        assert cola[0]["clase_error"] == "datos"

        alertas = json.loads(inventario_limpio["alertas"].read_text())
        assert alertas[0]["clase_error"] == "datos"

    @pytest.mark.parametrize("estado_proceso,clase", [
        ("error_datos", "datos"),
        ("error_transitorio", "transitorio"),
        ("error_sistema", "sistema"),
    ])
    def test_error_en_a01_registra_su_clase(
        self, monkeypatch, datos_base, inventario_limpio, estado_proceso, clase
    ):
        fn_a01 = _nodo_a01_fake(True, "alta", 22, estado_proceso=estado_proceso)
        fn_a02 = _nodo_a02_fake(_propuesta_paracetamol(22))
        fn_a03 = _nodo_a03_fake("APROBADO")

        _ejecutar(monkeypatch, fn_a01, fn_a02, fn_a03, datos_base, inventario_limpio)

        cola = self._cola_fin_error(inventario_limpio)
        assert len(cola) == 1
        assert cola[0]["clase_error"] == clase


# ---------------------------------------------------------------------------
# Flujo completo con los agentes reales y el LLM falso
# ---------------------------------------------------------------------------

class TestGrafoAgentesReales:
    """Paracetamol (8, 15, cantidad 22) con los tres agentes reales → AUTO_BORRADOR."""

    def test_paracetamol_auto_borrador(self, monkeypatch, llm_falso, datos_base, inventario_limpio):
        from botica.agentes.a01_inventario import nodo_a01_inventario
        from botica.agentes.a02_abastecimiento import nodo_a02_abastecimiento
        from botica.agentes.a03_validador import nodo_a03_validador
        from botica.estado.esquemas import RedaccionInventario

        llm_falso.configurar(RedaccionInventario, RedaccionInventario(analisis="Stock bajo."))
        llm_falso.configurar(
            PropuestaAbastecimiento,
            PropuestaAbastecimiento(**_propuesta_paracetamol(22)),
        )
        llm_falso.configurar(
            SalidaValidador, SalidaValidador(resultado="APROBADO", observaciones=[])
        )
        for modulo in ("a01_inventario", "a02_abastecimiento", "a03_validador"):
            monkeypatch.setattr(f"botica.agentes.{modulo}.crear_llm", lambda: llm_falso)

        entrada = {**datos_base, "cantidad_solicitada": 22}
        resultado = _ejecutar(
            monkeypatch, nodo_a01_inventario, nodo_a02_abastecimiento, nodo_a03_validador,
            entrada, inventario_limpio,
        )

        assert resultado["prioridad"] == "alta"
        assert resultado["cantidad_sugerida"] == 22
        assert resultado["decision_hitl"] == "AUTO_BORRADOR"
        assert resultado["solicitud_registrada"]["estado_solicitud"] == "PENDIENTE_COTIZACION"
        assert resultado["solicitud_registrada"]["cantidad_solicitada"] == 22
        # Una llamada por agente, sin llamadas extra
        assert len(llm_falso.llamadas) == 3
