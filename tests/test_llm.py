"""Clientes LLM sin red: formato de la petición y elección de backend por el entorno."""

import io
import json

import pytest

from pitchiq.agent import llm


def test_cliente_openai_compatible_envia_system_y_user(monkeypatch):
    enviado = {}

    def falso_urlopen(req, timeout):
        enviado.update(url=req.full_url, body=json.loads(req.data), auth=req.headers.get("Authorization"))
        return io.BytesIO(json.dumps({"choices": [{"message": {"content": "PPDA {metrica.ppda}"}}]}).encode())

    monkeypatch.setattr(llm.urllib.request, "urlopen", falso_urlopen)
    c = llm.OpenAICompatibleClient("http://localhost:11434/v1/", "qwen", api_key="k")
    assert c.complete("sys", "usr") == "PPDA {metrica.ppda}"
    assert enviado["url"] == "http://localhost:11434/v1/chat/completions"
    assert [m["role"] for m in enviado["body"]["messages"]] == ["system", "user"]
    assert enviado["auth"] == "Bearer k"


def test_eleccion_de_backend(monkeypatch):
    for var in ("PITCHIQ_LLM_URL", "PITCHIQ_MODELO", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("PITCHIQ_LLM_URL", "http://localhost:11434/v1")
    with pytest.raises(RuntimeError, match="PITCHIQ_MODELO"):
        llm.cliente_por_defecto()
    monkeypatch.setenv("PITCHIQ_MODELO", "qwen")
    assert isinstance(llm.cliente_por_defecto(), llm.OpenAICompatibleClient)
    monkeypatch.delenv("PITCHIQ_LLM_URL")
    monkeypatch.setattr(llm.shutil, "which", lambda _: "/usr/bin/claude")
    assert isinstance(llm.cliente_por_defecto(), llm.ClaudeCodeClient)
