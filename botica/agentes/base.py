"""
Módulo base del LLM: crea el modelo de lenguaje Groq con parámetros configurables.
La función crear_llm es inyectable en los tests para evitar llamadas reales a la API.
"""
from __future__ import annotations

import os

from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq

load_dotenv()

MODELO_NOMBRE = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
MAX_TOKENS = int(os.getenv("GROQ_MAX_TOKENS", "800"))


def crear_llm() -> ChatGroq:
    """
    Crea y devuelve el LLM de Groq configurado con variables de entorno.
    Inyectable para pruebas: en tests se reemplaza con un LLMFalso.
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY no está definida en el entorno")
    return ChatGroq(
        model=MODELO_NOMBRE,
        api_key=api_key,
        max_tokens=MAX_TOKENS,
    )


def crear_plantilla(prompt_sistema: str) -> ChatPromptTemplate:
    """
    Plantilla de prompt LCEL de los agentes: mensaje de sistema fijo + mensaje humano
    con la variable {entrada}. El texto del sistema se escapa para que sus llaves no se
    tomen como variables de la plantilla.
    """
    sistema = prompt_sistema.replace("{", "{{").replace("}", "}}")
    return ChatPromptTemplate.from_messages(
        [("system", sistema), ("human", "{entrada}")]
    )
