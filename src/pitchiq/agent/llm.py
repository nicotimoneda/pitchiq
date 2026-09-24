"""Wrapper agnóstico de proveedor de LLM: interfaz fina + dos backends.

El LLM solo redacta: nunca computa métricas. Cambiar de proveedor = implementar
``LLMClient`` con otro backend e inyectarlo donde se use.

- ``AnthropicClient``: Messages API con ANTHROPIC_API_KEY (se factura aparte).
- ``ClaudeCodeClient``: el CLI ``claude`` en modo no interactivo, con la sesión
  de la suscripción de Claude del usuario. Sin key.
"""

import json
import os
import shutil
import subprocess
from typing import Protocol

DEFAULT_MODEL = "claude-opus-5-5"


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

        self.model = self.model_used = model
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


class ClaudeCodeClient:
    """Redacta con ``claude -p``: usa la sesión iniciada en el CLI (suscripción), sin key.

    Sin herramientas, sin ajustes del usuario (CLAUDE.md, hooks) y sin guardar la
    sesión: el modelo solo ve el prompt de sistema y el de usuario, como en la API.
    """

    def __init__(self, model: str = "opus", timeout: int = 600) -> None:
        """Comprueba que el CLI está instalado."""
        if not shutil.which("claude"):
            raise RuntimeError("No encuentro el CLI `claude`. Instálalo: https://claude.com/claude-code")
        self.model = model
        self.timeout = timeout

    def complete(self, system: str, user: str) -> str:
        """Una llamada al CLI; el prompt de usuario va por stdin."""
        # dentro de otra sesión de Claude Code el CLI se negaría a arrancar anidado
        env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "ANTHROPIC_API_KEY")}
        proc = subprocess.run(
            ["claude", "-p", "--output-format", "json", "--model", self.model,
             "--system-prompt", system, "--tools", "", "--setting-sources", "",
             "--no-session-persistence"],
            input=user, capture_output=True, text=True, timeout=self.timeout, env=env,
        )
        try:
            out = json.loads(proc.stdout)
        except json.JSONDecodeError:
            raise RuntimeError(f"`claude -p` falló: {proc.stderr.strip() or proc.stdout[:300]}") from None
        if out.get("is_error"):
            msg = out.get("result", "")
            if "authenticate" in msg.lower() or "login" in msg.lower():
                msg += " — abre `claude` en una terminal y ejecuta /login con tu cuenta de Claude."
            raise RuntimeError(f"`claude -p` devolvió un error: {msg}")
        self.model_used = next(iter(out.get("modelUsage") or {}), self.model)
        return out["result"]


def cliente_por_defecto() -> LLMClient:
    """API si hay ANTHROPIC_API_KEY; si no, el CLI de Claude con la suscripción."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return AnthropicClient()
    return ClaudeCodeClient(model=os.environ.get("PITCHIQ_MODELO", "opus"))
