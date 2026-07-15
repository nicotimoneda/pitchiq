# Evaluación honesta de PitchIQ

Este documento reúne lo que el sistema **puede afirmar con evidencia**, lo que
**no afirma**, y **todas sus limitaciones sin maquillar**. Los números salen de
`eval/results/` (regenerables con `uv run python scripts/run_eval.py`).

## Qué afirma el sistema (y qué no)

PitchIQ **NO afirma** que "scoutea mejor que un humano", ni que sus informes
sustituyan a un analista. Lo que afirma, con evidencia:

1. **Grounding total verificado.** Cada cifra del informe publicado proviene de
   una métrica computada y un validador automático lo comprueba cifra a cifra.
2. **Retrieval medido, no supuesto.** La capa RAG se evalúa con RAGAS
   (fidelidad, relevancia de contexto) y con top-k accuracy; los resultados se
   publican aunque no favorezcan las decisiones tomadas (ver embeddings).
3. **Motor de métricas que generaliza.** Las métricas deterministas corren sin
   cambios sobre un torneo distinto (Euro 2024).
4. **Comunicación trazable.** El informe publica su evidencia completa
   (`/api/evidence`) y advierte del estado de revisión de sus interpretaciones.

## Resultados

### Grounding (validador de M4 sobre el informe servido)

| Métrica | Valor |
|---|---|
| Cifras en el informe | 3/3 respaldadas |
| Ratio de grounding | **1.0** |

*Nota:* medido sobre los artefactos actualmente servidos (fixtures de muestra;
los artefactos reales se generan con `scripts/precompute.py` y el mismo check
se re-ejecuta sobre ellos — hay un test que lo garantiza en CI).

### Comparación de embeddings (top-k accuracy, 10 preguntas, sin LLM)

| Modelo | top-1 | top-3 |
|---|---|---|
| `all-MiniLM-L6-v2` (M5, monolingüe inglés) | **80 %** | **100 %** |
| `paraphrase-multilingual-MiniLM-L12-v2` (M6) | 60 % | 90 % |

**Hallazgo incómodo y honesto:** el cambio a embeddings multilingües de M6 se
decidió tras probar a ojo 2-3 consultas donde el modelo inglés fallaba. Medido
sobre el set completo, **el cambio empeoró el retrieval** (−20 puntos de top-1).
La lección es el propio método: validar a ojo con ejemplos sueltos engaña;
hay que medir sobre un set. **Resolución: revertido a `all-MiniLM-L6-v2` en M7**,
esta vez con el número delante. *Caveat del caveat:* el set son 10 preguntas —
cada pregunta vale 10 puntos, así que la diferencia real son 2 preguntas.

### Evaluación RAGAS (fidelidad + relevancia de contexto)

Requiere LLM juez (API key) y corre fuera de CI:
`ANTHROPIC_API_KEY=... uv run --script scripts/eval_rag.py`
→ resultados en `eval/results/ragas.json`. **Estado: pendiente de corrida por
el autor** (este repositorio no ejecuta llamadas de LLM en CI ni en sesiones
sin key; el hueco se rellena con la corrida real, no con un número inventado).

### Generalización (Euro 2024, solo métricas deterministas, sin key)

Motor de métricas M1-M3 sin ningún cambio sobre España (campeona, 7 partidos),
ids de competición resueltos dinámicamente del catálogo (55/282):

| Métrica | España Euro 2024 | Leverkusen 23/24 (referencia) |
|---|---|---|
| Acciones defensivas / partido | 227.0 | 213.8 |
| PPDA medio | 2.15 | 2.48 |
| Área de hull media (m²) | 529.4 | 514 |
| Altura de línea media | 53.8 | 52.9 |
| Córners a favor / en contra | 45 / 20 | 236 / 112 |
| xG córner a favor / en contra | 1.69 / 0.67 | 10.84 / 4.95 |
| Partidos con 360 | 7/7 | 31/34 |

El motor corre sin crashear ni ajustes, y los valores caen en rangos plausibles
y comparables. La cobertura 360 **varía entre torneos y partidos** (aquí 7/7;
en la Bundesliga 23/24, 31/34): toda métrica espacial hereda esa dependencia.

## Todas las limitaciones, juntas

1. **Área visible de los 360.** Los freeze-frames solo capturan a los jugadores
   en el plano de la retransmisión: nunca se asumen 22 (ni 11) por frame. Toda
   métrica espacial es una aproximación sobre visibles y los conteos son cotas
   inferiores. 3 de los 34 partidos del Leverkusen no tienen 360.
2. **Dataset pequeño y de un solo sujeto.** 34 partidos del Leverkusen 23/24.
   Suficiente para patrones agregados de UN equipo; nada de conclusiones de
   liga ni comparaciones entre equipos con muestras distintas.
3. **El MOI es un proxy heurístico.** Distancia media al marcador más cercano
   sobre visibles. No clasifica sistemas de marcaje ni detecta esquemas mixtos.
4. **Glosario en revisión.** Las interpretaciones tácticas las redactó una IA
   como borrador: 10/10 entradas con `revisado: false`, sin fuentes citadas
   (para no fabricarlas). No son autoritativas hasta revisión humana.
5. **Muestras de córners.** 236 a favor / 112 en contra: bien para agregados,
   justo para subdivisiones finas (p. ej. "córners al segundo palo en la
   segunda parte" son ya submuestras minúsculas).
6. **Embeddings en español.** Ver tabla: la configuración final (revertida
   tras medir) da 80 % top-1 / 100 % top-3 sobre un set de 10 preguntas; la
   decisión "de mejora" de M6 fue una regresión medible (−20 top-1). Set
   pequeño: cada pregunta mueve un 10 %.
7. **PPDA no estándar.** Incluye eventos Pressure: los valores (~2-3) no son
   comparables con el PPDA clásico estilo Opta (~8-15). Consistente
   internamente, no entre implementaciones.
8. **El LLM redacta, con red de seguridad.** El grounding garantiza las cifras,
   no la calidad táctica de la prosa: una frase puede ser sosa o genérica y
   pasar el validador igualmente.

## Reproducir

```bash
uv run python scripts/run_eval.py            # grounding + embeddings + Euro 2024 (sin key)
ANTHROPIC_API_KEY=... uv run --script scripts/eval_rag.py   # RAGAS (con key, fuera de CI)
```
