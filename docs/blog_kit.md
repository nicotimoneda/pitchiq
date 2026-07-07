# Kit de blog — PitchIQ

> ⚠️ **MATERIAL EN CRUDO — reescribir en voz propia, NO publicar tal cual.**
> Esto es una colección de hechos, números y un esquema sugerido. La prosa
> final la escribe el autor: un post redactado por IA se nota y resta
> credibilidad, que es exactamente lo contrario de lo que defiende el proyecto.

## Hallazgos con sus números (ordenados por interés, no por cronología)

### 1. El fix "obvio" que empeoró el sistema (el hallazgo más contable)
- En M5 se detectó "a ojo" que los embeddings ingleses (`all-MiniLM-L6-v2`)
  fallaban consultas en español; en M6 se cambió a un modelo multilingüe.
- Al medir en M7 con top-k accuracy sobre el set de 10 preguntas:
  **inglés 80 % top-1 / 100 % top-3 vs multilingüe 60 % / 90 %**.
  El fix fue una regresión de −20 puntos.
- Moral: validar con 2-3 ejemplos elegidos a mano es una trampa; sin un set de
  evaluación, hasta las mejoras "evidentes" pueden ser regresiones.
- Caveat que hay que contar: el set son 10 preguntas; cada una vale 10 puntos.

### 2. El invariante de grounding (la tesis del proyecto)
- Regla dura: el LLM no calcula ni una cifra; solo redacta sobre salidas de
  herramientas deterministas. Un validador extrae cada número del texto y lo
  coteja contra la evidencia (tolerando redondeo y coma decimal española).
- Si una cifra no casa: una regeneración con feedback; si persiste, se publica
  marcada como no verificada. Nunca se maquilla.
- Ratio medido sobre el informe servido: **1.0** (re-validado en CI por test).
- Detalle técnico contable: años y "2023/24" se excluyen del check; "52,9"
  respalda a 52.87.

### 3. RAG que no puede alucinar números (la trampa evitada)
- Trampa clásica: añades RAG "para enriquecer" y el retrieval mete cifras de
  otros contextos que el LLM recicla → alucinación con pedigrí.
- Solución estructural, no de prompt: el glosario RAG tiene un validador
  pydantic que **rechaza cualquier entrada con dígitos**. El RAG solo puede
  aportar interpretación (qué significa un PPDA bajo), jamás valores.
- Además: glosario redactado por IA marcado entero `revisado: false`, sin
  fuentes citadas (mejor campo vacío que una cita fabricada).

### 4. La identidad táctica del Leverkusen que emerge de los datos
- PPDA medio 2.48 (con Pressure incluido; no comparable con Opta) y 53.1 % de
  las acciones defensivas en campo rival → presión adelantada sistemática.
- Línea defensiva media en 52.9 (mitad de campo) y bloque de 514 m² de hull
  medio (35.6 de ancho × 23.9 de profundidad).
- Balón parado dominante: 236 córners a favor vs 112 en contra; 68.2 % de
  primer contacto ganado atacando; 10.84 xG generado vs 4.95 concedido.
- Reparto de saques: 74 cortos / 67 al centro / 62 al primer palo / 33 al
  segundo — el córner corto como seña (31 % de los saques).
- MOI defensivo medio 3.37 m (proxy: tendencia mixta, ni hombre puro ni zona).

### 5. El motor generaliza (Euro 2024, cero cambios de código)
- España campeona: 7 partidos, PPDA 2.15, línea 53.8, hull 529 m², 45 córners
  a favor. Ids del torneo resueltos del catálogo (55/282), no hardcodeados.
- Cobertura 360: 7/7 en la Euro vs 31/34 en Bundesliga — toda métrica espacial
  hereda esa variabilidad y hay que decirlo.

### 6. Arquitectura precomputada (el ángulo de producto/coste)
- Generación (LLM, cara) una vez en local con la key del autor; producción
  sirve artefactos estáticos: imagen Docker sin torch/langgraph/anthropic
  (CI lo verifica con un grep sobre pip list), cero secretos, coste por
  visita = cero.
- Bonus de guerra: ragas es incompatible con langchain 1.x → la evaluación
  corre en un entorno aislado con pins propios (script PEP 723).

## Esquema sugerido (estilo del post del WGAN: liderar con lo incómodo)

1. **Gancho:** "Cambié los embeddings para arreglar el español. Medido después:
   20 puntos peor." (el hallazgo 1, no el proyecto)
2. **El problema real:** informes tácticos con LLM = números inventados con
   confianza. Qué significa "grounded" aquí (hallazgo 2).
3. **Cómo se construyó el invariante:** tools deterministas → validador →
   reintento → marca. El RAG capado de números (hallazgo 3).
4. **Qué dicen los datos del Leverkusen** (hallazgo 4, con 2-3 figuras).
5. **La prueba de generalización** (hallazgo 5, tabla España vs Leverkusen).
6. **Todo lo que NO puede afirmar el sistema:** resumen de EVALUATION.md,
   incluida la lección de los embeddings completa.
7. **Cierre:** el sistema no scoutea mejor que un humano; comunica mejor que
   un LLM suelto. Enlace a la demo y al repo.

## Datos y figuras disponibles para ilustrar

- `app/static/report/figures/` (tras precompute) y `figures/` locales:
  - bloque defensivo (KDE) temporada + línea por partido (con huecos sin 360)
  - mapa de recuperaciones 6×5 con PPDA
  - saques de córner (heatmap + conteos por zona), box load, primer contacto
    a favor/en contra
- `eval/results/*.json`: grounding, embeddings (antes/después), generalización
- `EVALUATION.md`: tabla completa de limitaciones para el punto 6
- El informe servido y su evidencia: `/`, `/api/report`, `/api/evidence`

## Números pendientes de rellenar por el autor (con key)

- RAGAS faithfulness / context_relevance (`eval/results/ragas.json`)
- Ratio de grounding del informe REAL precomputado (hoy: fixtures de muestra)
- LIVE URL del deploy en Render
