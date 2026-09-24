# Evaluación honesta de PitchIQ

Este documento reúne lo que el sistema **puede afirmar con evidencia**, lo que
**no afirma**, y **todas sus limitaciones sin maquillar**. Los números salen de
`eval/results/` (regenerables con `uv run python scripts/run_eval.py`).

## Qué afirma el sistema (y qué no)

PitchIQ **NO afirma** que "scoutea mejor que un humano", ni que sus informes
sustituyan a un analista. Lo que afirma, con evidencia:

1. **Grounding por citas.** El redactor no escribe cifras: cita claves de un
   dossier calculado con los datos y el código inserta los valores. Un
   verificador comprueba cada cita y rechaza cualquier dígito escrito a mano,
   aunque coincida por casualidad con un valor real.
2. **Retrieval medido, no supuesto.** La capa RAG se evalúa con RAGAS
   (fidelidad, relevancia de contexto) y con top-k accuracy; los resultados se
   publican aunque no favorezcan las decisiones tomadas (ver embeddings).
3. **Motor de métricas que generaliza.** Las métricas deterministas corren sin
   cambios sobre un torneo distinto (Euro 2024).
4. **Comunicación trazable.** Cada informe se publica con el borrador tal cual,
   el dossier que recibió el modelo y su verificación
   (`/api/equipos/{slug}/informe`), y la web enseña la fuente de cada cifra.

## Resultados

### Grounding (verificador de citas sobre los informes servidos)

`scripts/run_eval.py` no se fía de lo guardado al generar: vuelve a pasar el
verificador sobre el borrador de cada informe (ES y EN) y el dossier que recibió.

| Métrica | Valor |
|---|---|
| Citas válidas / cifras en los informes | ver `eval/results/grounding.json` |
| Percentiles del dossier (Python) frente a los de la web (JavaScript) | **2617 / 2617** idénticos |

*Nota:* mientras no se generen los informes reales, la medida corre sobre el
informe de muestra; hay un test en CI que exige ratio 1,0 sobre lo servido.
Límite conocido: el verificador detecta cifras con dígitos, no cantidades
escritas con letras («tres victorias»). El prompt lo prohíbe, pero no se comprueba.

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

### Validación externa (Understat, 1.621 partidos, sin key)

Las métricas publicadas se contrastan partido a partido con una fuente pública
independiente, [Understat](https://understat.com), para los 43 equipos de club
(las selecciones no entran: Understat no cubre torneos). La foto de Understat está
versionada en `eval/external/understat.json` con su fecha de acceso; el cruce es por
fecha (±1 día) y campo, y el resultado queda en `eval/results/externa.json`.

| Qué se compara | Resultado | Lectura |
|---|---|---|
| Goles a favor y en contra | **1.621 / 1.621 partidos idénticos** | La ingesta y el cruce de partidos son correctos. |
| xG a favor por partido | **correlación 0,93**; el nuestro (StatsBomb) sale 0,06 más bajo de media | Dos modelos distintos que coinciden en qué partidos generaron más peligro. |
| PPDA clásico (sin presiones) | **Spearman 0,93 entre equipos**; correlación 0,83 partido a partido | Con la definición estándar, nuestros datos ordenan a los equipos como la fuente pública. |
| PPDA de la web (con presiones) | Spearman 0,74; valores ~3,5 veces más bajos | Se parece, pero menos: mide **volumen de presión**, no cuánto se corta el juego rival. |

<details>
<summary>Tabla completa de los 43 equipos (nuestro / Understat)</summary>

| Equipo | Partidos | Goles a favor | xG a favor / partido | PPDA (con presiones) | PPDA clásico |
|---|---|---|---|---|---|
| AFC Bournemouth (Premier League 2015/16) | 38 | 45 / 45 | 1,06 / 1,02 | 2,48 / 9,58 | 13,80 / 9,58 |
| Arsenal (Premier League 2015/16) | 38 | 65 / 65 | 1,71 / 1,94 | 2,63 / 8,79 | 12,21 / 8,79 |
| Aston Villa (Premier League 2015/16) | 38 | 27 / 27 | 0,78 / 0,70 | 3,06 / 13,84 | 17,88 / 13,84 |
| Athletic Club (La Liga 2015/16) | 38 | 58 / 58 | 1,32 / 1,42 | 2,46 / 8,11 | 11,28 / 8,11 |
| Atlético Madrid (La Liga 2015/16) | 38 | 63 / 63 | 1,39 / 1,45 | 2,71 / 8,83 | 11,37 / 8,83 |
| Barcelona (La Liga 2015/16) | 38 | 112 / 112 | 2,41 / 2,99 | 2,13 / 6,01 | 9,35 / 6,01 |
| Barcelona (La Liga 2020/21) | 35 | 81 / 81 | 2,06 / 2,24 | 2,51 / 9,97 | 12,79 / 9,97 |
| Bayer Leverkusen (Bundesliga 2023/24) | 34 | 89 / 89 | 2,14 / 2,41 | 2,48 / 14,70 | 16,95 / 14,70 |
| Celta Vigo (La Liga 2015/16) | 38 | 51 / 51 | 1,32 / 1,32 | 2,30 / 6,44 | 9,23 / 6,44 |
| Chelsea (Premier League 2015/16) | 38 | 59 / 59 | 1,41 / 1,43 | 2,47 / 9,18 | 11,40 / 9,18 |
| Crystal Palace (Premier League 2015/16) | 38 | 39 / 39 | 1,12 / 1,12 | 2,60 / 9,33 | 12,21 / 9,33 |
| Eibar (La Liga 2015/16) | 38 | 49 / 49 | 1,32 / 1,39 | 2,48 / 7,80 | 10,29 / 7,80 |
| Espanyol (La Liga 2015/16) | 38 | 40 / 40 | 1,17 / 1,21 | 2,85 / 8,50 | 10,44 / 8,50 |
| Everton (Premier League 2015/16) | 38 | 59 / 59 | 1,33 / 1,42 | 2,92 / 12,47 | 14,05 / 12,47 |
| Getafe (La Liga 2015/16) | 38 | 37 / 37 | 1,04 / 1,10 | 2,68 / 9,87 | 11,61 / 9,87 |
| Granada (La Liga 2015/16) | 38 | 46 / 46 | 1,05 / 1,09 | 2,81 / 9,00 | 11,40 / 9,00 |
| Las Palmas (La Liga 2015/16) | 38 | 45 / 45 | 0,97 / 1,02 | 2,89 / 10,08 | 12,42 / 10,08 |
| Leicester City (Premier League 2015/16) | 38 | 68 / 68 | 1,74 / 1,80 | 2,81 / 10,10 | 14,09 / 10,10 |
| Levante UD (La Liga 2015/16) | 38 | 37 / 37 | 0,97 / 1,03 | 2,94 / 10,85 | 13,28 / 10,85 |
| Liverpool (Premier League 2015/16) | 38 | 63 / 63 | 1,54 / 1,43 | 2,09 / 7,92 | 10,36 / 7,92 |
| Málaga (La Liga 2015/16) | 38 | 38 / 38 | 1,14 / 1,20 | 2,77 / 7,83 | 10,74 / 7,83 |
| Manchester City (Premier League 2015/16) | 38 | 71 / 71 | 1,70 / 1,74 | 2,43 / 8,19 | 11,47 / 8,19 |
| Manchester United (Premier League 2015/16) | 38 | 49 / 49 | 1,11 / 1,20 | 2,34 / 8,07 | 10,64 / 8,07 |
| Newcastle United (Premier League 2015/16) | 38 | 44 / 44 | 1,07 / 0,99 | 2,91 / 12,39 | 13,98 / 12,39 |
| Norwich City (Premier League 2015/16) | 38 | 39 / 39 | 1,02 / 1,03 | 3,12 / 13,00 | 15,44 / 13,00 |
| PSG (Ligue 1 2022/23) | 32 | 80 / 80 | 2,05 / 2,29 | 2,71 / 11,96 | 12,96 / 11,96 |
| Rayo Vallecano (La Liga 2015/16) | 38 | 52 / 52 | 1,33 / 1,38 | 2,31 / 6,96 | 10,19 / 6,96 |
| RC Deportivo La Coruña (La Liga 2015/16) | 38 | 45 / 45 | 1,09 / 1,15 | 2,96 / 11,32 | 13,15 / 11,32 |
| Real Betis (La Liga 2015/16) | 38 | 34 / 34 | 1,05 / 1,06 | 3,02 / 11,12 | 12,95 / 11,12 |
| Real Madrid (La Liga 2015/16) | 38 | 110 / 110 | 2,13 / 2,38 | 2,79 / 9,25 | 11,31 / 9,25 |
| Real Sociedad (La Liga 2015/16) | 38 | 45 / 45 | 1,21 / 1,26 | 2,42 / 8,16 | 10,85 / 8,16 |
| Sevilla (La Liga 2015/16) | 38 | 51 / 51 | 1,60 / 1,66 | 2,72 / 8,60 | 11,24 / 8,60 |
| Southampton (Premier League 2015/16) | 38 | 59 / 59 | 1,43 / 1,48 | 2,63 / 9,65 | 12,44 / 9,65 |
| Sporting Gijón (La Liga 2015/16) | 38 | 40 / 40 | 1,08 / 1,12 | 3,08 / 11,57 | 12,98 / 11,57 |
| Stoke City (Premier League 2015/16) | 38 | 41 / 41 | 1,06 / 1,12 | 3,00 / 10,78 | 14,25 / 10,78 |
| Sunderland (Premier League 2015/16) | 38 | 48 / 48 | 1,12 / 1,07 | 3,22 / 12,60 | 14,86 / 12,60 |
| Swansea City (Premier League 2015/16) | 38 | 42 / 42 | 1,11 / 1,05 | 2,70 / 10,46 | 13,65 / 10,46 |
| Tottenham Hotspur (Premier League 2015/16) | 38 | 69 / 69 | 1,64 / 1,67 | 2,08 / 6,68 | 10,36 / 6,68 |
| Valencia (La Liga 2015/16) | 38 | 46 / 46 | 1,23 / 1,33 | 2,54 / 9,06 | 11,15 / 9,06 |
| Villarreal (La Liga 2015/16) | 38 | 44 / 44 | 0,98 / 1,07 | 3,22 / 9,92 | 12,42 / 9,92 |
| Watford (Premier League 2015/16) | 38 | 40 / 40 | 1,16 / 1,14 | 3,04 / 9,86 | 13,69 / 9,86 |
| West Bromwich Albion (Premier League 2015/16) | 38 | 34 / 34 | 1,02 / 1,05 | 3,16 / 12,34 | 16,43 / 12,34 |
| West Ham United (Premier League 2015/16) | 38 | 65 / 65 | 1,44 / 1,43 | 2,94 / 9,67 | 13,29 / 9,67 |

</details>

Tres cosas que esta comparación enseña y que no se veían sin mirar fuera:

- **La coincidencia exacta de goles es la prueba más dura y la más barata.** Un
  fallo de cruce de partidos, de local/visitante o de filtrado (como el que tuvo
  `_season_data` en torneos) rompería esa columna antes que ninguna otra.
- **El xG no es "el dato": es un modelo.** El de StatsBomb y el de Understat
  coinciden en el orden de los partidos pero no en la escala (la mayor diferencia,
  el Barça 2015/16: 2,41 frente a 2,99 por partido). Las cifras de xG de la web son
  las de StatsBomb y no deben mezclarse con las de otra fuente.
- **El PPDA con presiones no es el PPDA público.** Con la definición clásica
  calculada sobre los mismos eventos el orden coincide mucho más (0,93 frente a
  0,74), así que la diferencia es de definición y no un error del pipeline. Por
  eso la web enseña los dos y los percentiles de estilo usan el clásico. El
  clásico calculado aquí sale algo más alto que el de Understat (~1,3 veces):
  Understat no publica su lista exacta de acciones defensivas.

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
   (Spearman 0,74 frente a 0,93 del PPDA clásico calculado con los mismos
   eventos, en 43 equipos). Mide volumen de presión; para comparar con fuentes públicas hay
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
