"""Wrapper agnóstico de proveedor de LLM: interfaz fina + implementación Anthropic.

El LLM solo redacta: nunca computa métricas. Cambiar de proveedor = implementar
``LLMClient`` con otro backend e inyectarlo donde se use.
"""

import os
from typing import Protocol

DEFAULT_MODEL = "claude-opus-4-8"


class LLMClient(Protocol):
    """Interfaz mínima: mensajes de chat -> texto completado."""

    def complete(self, system: str, user: str) -> str:
        """Devuelve el texto de respuesta para un prompt de sistema + usuario."""
        ...


class AnthropicClient:
    """Implementación por defecto sobre la librería oficial ``anthropic``."""

    def __init__(self, model: str = DEFAULT_MODEL, max_tokens: int = 4096) -> None:
        """Crea el cliente leyendo la API key de ANTHROPIC_API_KEY (nunca hardcodeada)."""
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError(
                "Falta la variable de entorno ANTHROPIC_API_KEY. "
                "Expórtala antes de generar informes: "
                "export ANTHROPIC_API_KEY=sk-ant-..."
            )
        import anthropic  # import perezoso: los tests no necesitan el SDK real

        self.model = model
        self.max_tokens = max_tokens
        self._client = anthropic.Anthropic()

    def complete(self, system: str, user: str) -> str:
        """Llama a la Messages API y devuelve el texto concatenado de la respuesta."""
        response = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(
            block.text for block in response.content if block.type == "text"
        )
