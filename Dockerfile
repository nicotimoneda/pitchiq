# Imagen mínima: SOLO sirve artefactos precomputados. Nada de torch/langgraph/
# anthropic — la generación ocurre en local (scripts/precompute.py), no aquí.
FROM python:3.12-slim AS deps

COPY --from=ghcr.io/astral-sh/uv:0.9.13 /uv /bin/uv
WORKDIR /srv
COPY pyproject.toml uv.lock ./
# exporta SOLO el grupo "app" del lockfile (fastapi, uvicorn, jinja2, markdown)
RUN uv export --only-group app --no-emit-project --no-hashes -o requirements.txt

FROM python:3.12-slim

WORKDIR /srv
COPY --from=deps /srv/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && rm requirements.txt

# la app y sus artefactos precomputados (métricas e informes por equipo)
COPY app/ app/

# sin privilegios: la app solo lee sus artefactos
RUN useradd --create-home --shell /usr/sbin/nologin app
USER app

EXPOSE 8000
# $PORT si lo define el entorno; 8000 por defecto
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips=*"]
