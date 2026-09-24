# Cómo se generan los informes

La web nunca llama a un modelo. Los informes se escriben antes, en la máquina del autor, se revisan y se suben al repositorio como archivos. Así la web pública no necesita API key y cualquier informe se puede auditar.

**Qué pasa con cada equipo**, una vez en español y otra en inglés:

1. `construir_dossier` calcula unos 85 datos con clave y sus percentiles a partir de los datos del equipo.
2. El buscador del glosario añade qué significan las métricas relevantes (opcional; sin dígitos).
3. El redactor escribe el borrador citando `{claves}` en lugar de escribir números.
4. El verificador comprueba cada cita. Si algo falla, el borrador vuelve una vez con la lista exacta de fallos. Lo que siga fallando se guarda y se enseña como *sin respaldo*.

**Cómo lanzarlo:**

```bash
uv run python scripts/build_index.py                                     # índice del glosario (una vez; opcional)
uv run python scripts/precompute.py --equipos bayer-leverkusen-2023-24   # uno o varios equipos, separados por comas
uv run python scripts/precompute.py --solo-faltan                        # todos los equipos que aún no tienen informe
```

Cada informe se guarda en cuanto termina, así que una tanda larga se puede cortar y reanudar con `--solo-faltan`. La consola enseña, por idioma, las citas válidas, las cifras sin respaldo y los reintentos.

**El modelo se elige** con variables de entorno. Gana la primera que esté definida:

| Backend | Cómo | Coste |
|---|---|---|
| Modelo local ([Ollama](https://ollama.com), LM Studio…) | `PITCHIQ_LLM_URL=http://localhost:11434/v1 PITCHIQ_MODELO=qwen2.5:14b` | gratis |
| Cualquier API compatible con OpenAI | `PITCHIQ_LLM_URL=… PITCHIQ_MODELO=… PITCHIQ_LLM_KEY=…` | lo que cobre el proveedor |
| API de Anthropic | `ANTHROPIC_API_KEY=…` (modelo: `PITCHIQ_MODELO`, por defecto `claude-opus-5-5`) | precio de la API |
| Suscripción de Claude | nada: usa el CLI `claude` (`claude` → `/login` una vez; modelo: Opus, o `PITCHIQ_MODELO`) | tu plan |

Si guardas las keys en un archivo `.env`, git lo ignora. Una key nunca viaja sin cifrar (HTTP) a un servidor remoto.

**Qué se guarda**, en `app/static/report/informes/<slug>.json`:

| Campo | Contenido |
|---|---|
| `es`, `en` | el borrador tal cual lo escribió el modelo (Markdown con `{claves}`), citas válidas, cifras sin respaldo y reintentos |
| `dossier` | cada dato que el modelo podía citar, con su valor y su descripción |
| `contexto` | las entradas del glosario que recibió |
| `modelo`, `generated_at` | qué modelo lo escribió y cuándo |

La web pinta el borrador, cambia cada `{clave}` por su valor y enlaza cada cifra con su fuente. El archivo tal cual es público en `/api/equipos/<slug>/informe`. Los equipos sin informe enseñan un resumen determinista hecho con el mismo dossier y comprobado igual.

**Antes de subirlo**, se vuelve a verificar todo lo que se va a servir:

```bash
uv run python scripts/run_eval.py --skip-generalization    # repasa con el verificador cada borrador guardado
```

Entre ejecuciones, y entre modelos, cambia la prosa. Lo que no puede cambiar es una cifra: un modelo más flojo que ignore la regla de citar ve sus números rechazados y marcados como sin respaldo. Un modelo local de 7B hizo exactamente eso en las pruebas, y para eso está el diseño. Lo que el verificador no puede detectar es una afirmación cualitativa sin números; por eso el borrador y el dossier están siempre a un clic ([detalles](../EVALUATION.md)).
