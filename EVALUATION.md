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
| Área de hull media (m²) | 442.7 | 430 |
| Altura de línea media (m desde su portería) | 49.2 | 48.4 |
| Córners a favor / en contra | 45 / 20 | 236 / 112 |
| xG córner a favor / en contra | 1.69 / 0.67 | 10.84 / 4.95 |
| Partidos con 360 | 7/7 | 31/34 |

El motor corre sin crashear ni ajustes, y los valores caen en rangos plausibles
y comparables. La cobertura 360 **varía entre torneos y partidos** (aquí 7/7;
en la Bundesliga 23/24, 31/34): toda métrica espacial hereda esa dependencia.

### Validación externa (Understat, 481 partidos, sin key)

Las métricas publicadas se contrastan partido a partido con una fuente pública
independiente, [Understat](https://understat.com), para los 13 equipos de club
(las selecciones no entran: Understat no cubre torneos). La foto de Understat está
versionada en `eval/external/understat.json` con su fecha de acceso; el cruce es por
fecha (±1 día) y campo, y el resultado queda en `eval/results/externa.json`.

| Qué se compara | Resultado | Lectura |
|---|---|---|
| Goles a favor y en contra | **481 / 481 partidos idénticos** | La ingesta y el cruce de partidos son correctos. |
| xG a favor por partido | **correlación 0,94**; el nuestro (StatsBomb) sale 0,15 más bajo de media | Dos modelos distintos que coinciden en qué partidos generaron más peligro; StatsBomb es más conservador. |
| PPDA clásico (sin presiones) | **Spearman 0,97 entre equipos**; correlación 0,87 partido a partido | Con la definición estándar, nuestros datos ordenan a los equipos como la fuente pública. |
| PPDA de la web (con presiones) | Spearman 0,48; valores ~3,5 veces más bajos | Mide otra cosa: **volumen de presión**, no cuánto se corta el juego rival. |

| Equipo | Partidos | Goles a favor (nuestro / Understat) | xG a favor por partido | PPDA con presiones | PPDA clásico |
|---|---|---|---|---|---|
| Athletic Club (La Liga 2015/16) | 38 | 58 / 58 | 1,32 / 1,42 | 2,46 / 8,11 | 11,28 / 8,11 |
| Atlético Madrid (La Liga 2015/16) | 38 | 63 / 63 | 1,39 / 1,45 | 2,71 / 8,83 | 11,37 / 8,83 |
| Barcelona (La Liga 2015/16) | 38 | 112 / 112 | 2,41 / 2,99 | 2,13 / 6,01 | 9,35 / 6,01 |
| Barcelona (La Liga 2020/21) | 35 | 81 / 81 | 2,06 / 2,24 | 2,51 / 9,97 | 12,79 / 9,97 |
| Bayer Leverkusen (Bundesliga 2023/24) | 34 | 89 / 89 | 2,14 / 2,41 | 2,48 / 14,70 | 16,95 / 14,70 |
| Celta Vigo (La Liga 2015/16) | 38 | 51 / 51 | 1,32 / 1,32 | 2,30 / 6,44 | 9,23 / 6,44 |
| Málaga (La Liga 2015/16) | 38 | 38 / 38 | 1,14 / 1,20 | 2,77 / 7,83 | 10,74 / 7,83 |
| PSG (Ligue 1 2022/23) | 32 | 80 / 80 | 2,05 / 2,29 | 2,71 / 11,96 | 12,96 / 11,96 |
| Real Betis (La Liga 2015/16) | 38 | 34 / 34 | 1,05 / 1,06 | 3,02 / 11,12 | 12,95 / 11,12 |
| Real Madrid (La Liga 2015/16) | 38 | 110 / 110 | 2,13 / 2,38 | 2,79 / 9,25 | 11,31 / 9,25 |
| Real Sociedad (La Liga 2015/16) | 38 | 45 / 45 | 1,21 / 1,26 | 2,42 / 8,16 | 10,85 / 8,16 |
| Sevilla (La Liga 2015/16) | 38 | 51 / 51 | 1,60 / 1,66 | 2,72 / 8,60 | 11,24 / 8,60 |
| Villarreal (La Liga 2015/16) | 38 | 44 / 44 | 0,98 / 1,07 | 3,22 / 9,92 | 12,42 / 9,92 |

Tres cosas que esta tabla enseña y que no se veían sin compararla con fuera:

- **La coincidencia exacta de goles es la prueba más dura y la más barata.** Un
  fallo de cruce de partidos, de local/visitante o de filtrado (como el que tuvo
  `_season_data` en torneos) rompería esa columna antes que ninguna otra.
- **El xG no es "el dato": es un modelo.** El de StatsBomb da menos xG que el de
  Understat en 13 de 13 equipos (la mayor diferencia, el Barça 2015/16: 2,41
  frente a 2,99 por partido). Las cifras de xG de la web son las de StatsBomb y no
  deben mezclarse con las de otra fuente.
- **Nuestro PPDA con presiones no ordena igual que el PPDA público.** Con la
  definición clásica calculada sobre los mismos eventos, el orden vuelve a coincidir
  (0,97), así que la diferencia es de definición y no un error del pipeline. El
  PPDA clásico calculado aquí sale algo más alto que el de Understat (~1,3 veces):
  Understat no publica su lista exacta de acciones defensivas, así que la escala
  no es comparable, pero el orden sí.

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
   comparables con el PPDA clásico estilo Opta (~8-15). Y no solo cambia la
   escala: medido contra Understat, **tampoco ordena igual a los equipos**
   (Spearman 0,48 frente a 0,97 del PPDA clásico calculado con los mismos
   eventos). Mide volumen de presión; para comparar con fuentes públicas hay
   que usar el clásico (`ppda_classic`, exportado como `ppda_clasico`).
8. **El LLM redacta, con red de seguridad.** El grounding garantiza las cifras,
   no la calidad táctica de la prosa: una frase puede ser sosa o genérica y
   pasar el validador igualmente.
9. **Unidades: las coordenadas vienen en yardas y se publican en metros.**
   StatsBomb normaliza el campo a 120×80 yardas. Una versión anterior del
   proyecto etiquetaba esos valores como metros sin convertirlos (incluida la
   descripción que leía el LLM); después se pasaron a yardas y, en septiembre de
   2026, a metros de verdad: las herramientas multiplican por 0,9144 (y las áreas
   por 0,9144²) antes de publicar, y los umbrales se definen en metros (apoyo en
   la presión a 10 m, robo alto a 40 m). El validador de grounding comprueba
   números, no unidades, así que un error de unidad no lo detectaría: por eso la
   conversión se hace en un único sitio (`config.a_metros`) y tiene test.

## Reproducir

```bash
uv run python scripts/run_eval.py            # grounding + embeddings + Euro 2024 (sin key)
uv run python scripts/validacion_externa.py  # contraste con Understat (foto versionada, sin red)
ANTHROPIC_API_KEY=... uv run --script scripts/eval_rag.py   # RAGAS (con key, fuera de CI)
```
