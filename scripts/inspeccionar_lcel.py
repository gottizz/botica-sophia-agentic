"""Muestra de qué Runnables LCEL está compuesta la cadena de un agente (sin llamar al LLM)."""
from langchain_groq import ChatGroq

from botica.agentes.base import crear_plantilla
from botica.estado.esquemas import SalidaValidador
from botica.herramientas.consultar_inventario import consultar_inventario

modelo = ChatGroq(model="openai/gpt-oss-20b", api_key="sin-llamada")
estructurado = modelo.with_structured_output(SalidaValidador)
cadena = (crear_plantilla("Eres el Agente Validador") | estructurado).with_config(run_name="A03 · Agente Validador")

print("with_structured_output →", type(estructurado).__name__, [type(p).__name__ for p in estructurado.steps])
print("cadena con .with_config →", type(cadena).__name__)
print("cadena interna          →", type(cadena.bound).__name__, [type(p).__name__ for p in cadena.bound.steps])
print("variables de la plantilla:", cadena.bound.first.input_variables)
print("@tool consultar_inventario →", type(consultar_inventario).__name__, "· es Runnable:",
      any(c.__name__ == "Runnable" for c in type(consultar_inventario).__mro__))
