"""
Pruebas del módulo de idempotencia.
Verifica la generación de claves SHA-256, códigos de solicitud y detección de duplicados.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from botica.reglas.idempotencia import (
    calcular_clave,
    generar_codigo,
    verificar_idempotencia,
)


def test_mismos_parametros_misma_clave() -> None:
    """Los mismos parámetros siempre producen la misma clave SHA-256."""
    clave1 = calcular_clave(25, "Sede Bolognesi 606", 22, "2026-01-15", 8)
    clave2 = calcular_clave(25, "Sede Bolognesi 606", 22, "2026-01-15", 8)
    assert clave1 == clave2
    assert len(clave1) == 64  # SHA-256 produce 64 hex chars


def test_parametros_distintos_claves_distintas() -> None:
    """Parámetros diferentes producen claves diferentes."""
    clave1 = calcular_clave(25, "Sede Bolognesi 606", 22, "2026-01-15", 8)
    clave2 = calcular_clave(25, "Sede Bolognesi 606", 22, "2026-01-15", 9)
    assert clave1 != clave2


def test_sede_se_normaliza_mayusculas() -> None:
    """Sede con mayúsculas se normaliza a minúsculas antes de calcular."""
    clave_minusc = calcular_clave(25, "sede bolognesi 606", 22, "2026-01-15", 8)
    clave_mayusc = calcular_clave(25, "SEDE BOLOGNESI 606", 22, "2026-01-15", 8)
    assert clave_minusc == clave_mayusc


def test_sede_se_normaliza_espacios() -> None:
    """Espacios extremos en la sede se eliminan en la normalización."""
    clave_limpia = calcular_clave(25, "Sede Bolognesi 606", 22, "2026-01-15", 8)
    clave_espacios = calcular_clave(25, "  Sede Bolognesi 606  ", 22, "2026-01-15", 8)
    assert clave_limpia == clave_espacios


def test_generar_codigo_formato_correcto() -> None:
    """El código debe seguir el patrón SOL-AAAAMMDD-XXXXXX."""
    clave = calcular_clave(25, "Sede Bolognesi 606", 22, "2026-01-15", 8)
    codigo = generar_codigo(clave, "2026-01-15")
    assert codigo.startswith("SOL-20260115-")
    partes = codigo.split("-")
    assert len(partes) == 3
    assert partes[0] == "SOL"
    assert partes[1] == "20260115"
    assert len(partes[2]) == 6
    assert partes[2] == partes[2].upper()


def test_generar_codigo_sufijo_de_clave() -> None:
    """El sufijo del código son los 6 primeros chars de la clave en mayúsculas."""
    clave = "abcdef1234567890" + "x" * 48
    codigo = generar_codigo(clave, "2026-03-10")
    assert codigo == "SOL-20260310-ABCDEF"


def test_verificar_idempotencia_archivo_inexistente(tmp_path: Path) -> None:
    """Si el archivo no existe, retorna (False, None)."""
    ruta = str(tmp_path / "no_existe.json")
    ya, existente = verificar_idempotencia("cualquier_clave", ruta)
    assert ya is False
    assert existente is None


def test_verificar_idempotencia_lista_vacia(tmp_path: Path) -> None:
    """Lista vacía → (False, None)."""
    ruta = tmp_path / "solicitudes.json"
    ruta.write_text("[]", encoding="utf-8")
    ya, existente = verificar_idempotencia("cualquier_clave", str(ruta))
    assert ya is False
    assert existente is None


def test_verificar_idempotencia_clave_existente(tmp_path: Path) -> None:
    """Si la clave ya está en el archivo → (True, solicitud_existente)."""
    clave = calcular_clave(25, "Sede Bolognesi 606", 22, "2026-01-15", 8)
    solicitud = {
        "codigo_solicitud": "SOL-20260115-ABCDEF",
        "clave_idempotencia": clave,
        "estado_solicitud": "PENDIENTE_COTIZACION",
    }
    ruta = tmp_path / "solicitudes.json"
    ruta.write_text(json.dumps([solicitud]), encoding="utf-8")

    ya, existente = verificar_idempotencia(clave, str(ruta))
    assert ya is True
    assert existente is not None
    assert existente["clave_idempotencia"] == clave


def test_verificar_idempotencia_clave_diferente_no_duplica(tmp_path: Path) -> None:
    """Si la clave en el archivo es diferente → (False, None)."""
    clave_en_archivo = calcular_clave(25, "Sede Bolognesi 606", 22, "2026-01-15", 8)
    clave_nueva = calcular_clave(31, "Sede Bolognesi 606", 40, "2026-01-15", 0)
    solicitud = {
        "clave_idempotencia": clave_en_archivo,
        "estado_solicitud": "PENDIENTE_COTIZACION",
    }
    ruta = tmp_path / "solicitudes.json"
    ruta.write_text(json.dumps([solicitud]), encoding="utf-8")

    ya, existente = verificar_idempotencia(clave_nueva, str(ruta))
    assert ya is False
    assert existente is None
