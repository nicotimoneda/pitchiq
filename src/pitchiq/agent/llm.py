"""Wrapper agnóstico de proveedor de LLM: interfaz fina + dos backends.

El LLM solo redacta: nunca computa métricas. Cambiar de proveedor = implementar
``LLMClient`` con otro backend e inyectarlo donde se use.

- ``AnthropicClient``: Messages API con ANTHROPIC_API_KEY (se factura aparte).
- ``ClaudeCodeClient``: el CLI ``claude`` en modo no interactivo, con la sesión
  de la suscripción de Claude del usuario. Sin key.
- ``OpenAICompatibleClient``: cualquier servidor con la API de chat de OpenAI
  (Ollama o LM Studio en local y gratis, vLLM, OpenAI...). Solo stdlib.
"""

import json
import os
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
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


class OpenAICompatibleClient:
    """Chat completions de cualquier servidor compatible con OpenAI (p. ej. Ollama en local)."""

    def __init__(self, url: str, model: str, api_key: "str | None" = None, timeout: int = 900) -> None:
        """``url`` es la base de la API, p. ej. http://localhost:11434/v1."""
        host = urllib.parse.urlsplit(url).hostname or ""
        if api_key and url.startswith("http://") and host not in ("localhost", "127.0.0.1", "::1"):
            raise RuntimeError(f"No envío la key sin cifrar a {host}: usa https://")
        self.url = url.rstrip("/") + "/chat/completions"
        self.model = self.model_used = model
        self.api_key = api_key
        self.timeout = timeout

    def complete(self, system: str, user: str) -> str:
        """Una petición de chat; temperatura baja para un informe sobrio."""
        body = json.dumps({"model": self.model, "temperature": 0.2, "messages": [
            {"role": "system", "content": system}, {"role": "user", "content": user}]}).encode()
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(self.url, data=body, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                out = json.load(resp)
        except urllib.error.URLError as e:
            raise RuntimeError(f"No hay respuesta de {self.url} ({e}). ¿Está arrancado el servidor "
                               "del modelo (p. ej. `ollama serve`)?") from None
        return out["choices"][0]["message"]["content"]


def cliente_por_defecto() -> LLMClient:
    """Elige backend por el entorno, del más explícito al más cómodo.

    1. PITCHIQ_LLM_URL: servidor compatible con OpenAI (Ollama, LM Studio, OpenAI...),
       con el modelo en PITCHIQ_MODELO y la key, si hace falta, en PITCHIQ_LLM_KEY.
    2. ANTHROPIC_API_KEY: la API de Anthropic.
    3. Si no: el CLI `claude` con la sesión de la suscripción.
    """
    if os.environ.get("PITCHIQ_LLM_URL"):
        if not os.environ.get("PITCHIQ_MODELO"):
            raise RuntimeError("Con PITCHIQ_LLM_URL indica también el modelo: PITCHIQ_MODELO=qwen2.5:14b")
        return OpenAICompatibleClient(os.environ["PITCHIQ_LLM_URL"], os.environ["PITCHIQ_MODELO"],
                                      os.environ.get("PITCHIQ_LLM_KEY"))
    if os.environ.get("ANTHROPIC_API_KEY"):
        return AnthropicClient(model=os.environ.get("PITCHIQ_MODELO", DEFAULT_MODEL))
    return ClaudeCodeClient(model=os.environ.get("PITCHIQ_MODELO", "opus"))
