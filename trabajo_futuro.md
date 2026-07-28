# Trabajo futuro: agentes para grafo de tramites

## Contexto actual

La POC actual recorre tramites de licencia de conducir de la Intendencia de Montevideo sin usar LLM ni frameworks agenticos.

El flujo actual es deterministico:

1. descarga HTML;
2. extrae titulo, secciones, links y formularios;
3. descubre enlaces internos relevantes;
4. visita una cantidad limitada de paginas;
5. genera grafo JSON, Mermaid y HTML interactivo.

## Enfoque acordado

Primero construir una arquitectura agentica sin LLM, para entender bien el flujo y mantener control del sistema.

Luego agregar LLM como una pasada selectiva sobre el grafo ya construido, no como navegador libre.

Flujo objetivo:

```text
crawler deterministico
  -> grafo crudo estructurado
  -> enriquecimiento LLM selectivo
  -> grafo semantico/de decision
```

## Objetivo del uso de LLM

El LLM no deberia recorrer todo desde cero ni decidir cada request.

Deberia trabajar sobre una estructura ya acotada para ahorrar tokens:

- nodos ya descubiertos;
- secciones relevantes ya extraidas;
- links filtrados;
- resumen por pagina;
- evidencia textual limitada.

## Fases propuestas

### Fase 1: crawling deterministico

- Mantener `requests` y `beautifulsoup4`.
- Mejorar descubrimiento de links.
- Separar paginas visitadas de paginas descubiertas.
- Mantener limites de dominio, profundidad y cantidad de paginas.

### Fase 2: agentes sin LLM

Crear agentes como clases Python simples, sin frameworks complejos:

```text
agents/
  explorer_agent.py
  extractor_agent.py
  classifier_agent.py
  graph_agent.py
  validator_agent.py
  reporter_agent.py
```

Responsabilidades:

- `ExplorerAgent`: descubre y prioriza enlaces.
- `ExtractorAgent`: extrae datos estructurados desde HTML.
- `ClassifierAgent`: clasifica links y paginas con reglas.
- `GraphAgent`: arma nodos y aristas.
- `ValidatorAgent`: detecta faltantes, duplicados e inconsistencias.
- `ReporterAgent`: genera JSON, Mermaid, HTML y resumen.

### Fase 3: enriquecimiento LLM selectivo

Agregar LLM como post-procesador semantico:

- clasificar tipo de tramite;
- identificar requisitos normalizados;
- detectar decisiones del usuario;
- detectar costos, agenda, formularios y documentos clave;
- marcar informacion faltante o ambigua.

Ejemplo de salida esperada por nodo:

```json
{
  "tipo_tramite": "renovacion",
  "requiere_agenda": true,
  "requiere_pago": true,
  "documentos_clave": ["cedula", "licencia anterior"],
  "siguientes_decisiones": [
    "licencia vigente o vencida",
    "categoria amateur o profesional"
  ],
  "riesgos_de_informacion": [
    "no se detecto costo exacto"
  ]
}
```

### Fase 4: grafo semantico/de decision

Construir una version enriquecida del grafo:

- nodos de tramite;
- nodos de requisito;
- nodos de costo;
- nodos de formulario;
- nodos de agenda;
- aristas semanticas como `requiere`, `continua_en`, `depende_de`, `agenda_en`.

## Criterios de exito

- El crawler captura el esqueleto del sitio sin LLM.
- El LLM solo analiza datos filtrados y estructurados.
- Cada dato enriquecido conserva evidencia de origen.
- El grafo final permite entender recorrido, requisitos y decisiones.
- La arquitectura sigue siendo didactica y extensible.
