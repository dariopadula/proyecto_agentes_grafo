# Herramienta de modelado de tramites

Esta carpeta alojara la herramienta asistida para que una persona no tecnica pueda construir y validar la logica de un tramite a partir de paginas web oficiales.

## Estado

Aplicacion local en desarrollo activo con:

- creacion de proyectos;
- deteccion y revision de links candidatos;
- persistencia de decisiones por CLI y navegador;
- exploracion de recursos internos;
- reglas configurables de filtrado;
- revision del uso y alcance de los recursos.
- analisis deterministico y agrupacion propuesta de PDF.
- inventario deterministico de enlaces auxiliares no documentales.

El siguiente paso es revisar los 14 recursos internos pendientes y validar una
excepcion individual sobre una decision heredada. Luego debe evaluarse la misma
materializacion para las decisiones de grupos PDF.

El MVP inicial esta definido en:

`cerebro_agentes_grafo/areas/herramienta_modelado_tramites/08_mvp_inicial.md`

El modelo de datos MVP esta definido en:

`cerebro_agentes_grafo/areas/herramienta_modelado_tramites/09_modelo_datos_mvp.md`

La carpeta `tramite_graph_poc/` queda como laboratorio exploratorio. Esta carpeta nueva debe evolucionar como herramienta limpia, orientada a uso por funcionarios.

## Objetivo

Permitir que un funcionario pueda:

1. ingresar la URL inicial de un tramite;
2. revisar links candidatos;
3. clasificar links como nodos terminales, informacion auxiliar, tramites relacionados, descartes o dudas;
4. explorar informacion secundaria de cada nodo terminal;
5. detectar informacion secundaria compartida entre nodos;
6. generar documentacion de nodos terminales y documentos auxiliares;
7. proponer preguntas canonicas para llegar a cada nodo terminal;
8. asociar preguntas extra para mejorar respuestas dentro del nodo final;
9. identificar relaciones entre tramites, nodos terminales y recursos auxiliares.

## Principios

- La herramienta debe ser asistida, no completamente automatica.
- Las decisiones importantes deben ser revisables por una persona.
- El crawler y los extractores deben proponer; el funcionario valida.
- El LLM puede ayudar a redactar, clasificar o sugerir relaciones, pero no debe borrar trazabilidad ni reemplazar revision humana.
- La informacion auxiliar debe evitar duplicacion y conservar fuentes.

## Productos esperados

- Grafo de ruteo con preguntas canonicas.
- Documentacion por nodo terminal.
- Documentacion auxiliar compartida.
- Relaciones entre nodos terminales y recursos.
- Reportes de revision para funcionarios.

## Relacion con la POC existente

`tramite_graph_poc/` contiene aprendizajes utiles:

- lectura web con `requests`;
- extraccion HTML con `beautifulsoup4`;
- deteccion de links del buscador;
- extraccion de campos Drupal y acordeones;
- paquetes de evidencia;
- pruebas de fichas LLM;
- visualizaciones HTML de grafos.

La nueva herramienta puede reutilizar ideas o codigo puntual, pero no debe quedar atada a decisiones experimentales de esa POC.

## Documentacion en el cerebro

El contexto vigente de esta herramienta vive en:

`cerebro_agentes_grafo/areas/herramienta_modelado_tramites/000_Inicio HMT.md`

## Instalacion

Desde esta carpeta:

```bash
pip install -r requirements.txt
```

## Uso actual

Crear un proyecto editable:

```bash
python app.py init-project --id licencia_conducir --name "Licencia de conducir" --url "https://tramites.montevideo.gub.uy/buscador_tramites/Licencia%20de%20conducir"
```

Esto genera:

- `data/projects/licencia_conducir/project.json`
- `data/projects/licencia_conducir/candidate_links.json`
- `data/projects/licencia_conducir/human_review.json`
- `data/projects/licencia_conducir/change_log.json`
- `data/projects/licencia_conducir/snapshots/`
- `outputs/licencia_conducir/`

El comando no descarga paginas todavia. Solo crea el proyecto vivo y los archivos base de trazabilidad.

Detectar links candidatos desde la URL inicial del proyecto:

```bash
python app.py discover-links --project-id licencia_conducir
```

Esto descarga la URL inicial, detecta links candidatos y actualiza:

- `data/projects/licencia_conducir/candidate_links.json`
- `data/projects/licencia_conducir/project.json`
- `data/projects/licencia_conducir/change_log.json`

El comando no clasifica links automaticamente. Solo prepara candidatos para revision humana.

Resultado validado con licencia de conducir: 22 links candidatos detectados.

Generar vista HTML estatica de revision:

```bash
python app.py build-review-links --project-id licencia_conducir
```

Esto genera:

- `outputs/licencia_conducir/review_links.html`

La vista permite buscar, filtrar y revisar los links candidatos. Esta salida sirve como reporte HTML, pero la edicion recomendada se hace desde la app local.

Los roles se muestran en espanol para el funcionario. Internamente se conservan codigos estables, por ejemplo `terminal_case` para "Caso terminal".

La vista tambien muestra roles secundarios para contemplar casos mixtos, por ejemplo un tramite de pago que puede ser caso terminal y tambien informacion auxiliar para otros nodos.

Guardar una decision humana sobre un link:

```bash
python app.py review-link --project-id licencia_conducir --link-id link_001 --primary-role terminal_case --confidence alta --notes "Caso terminal validado"
```

Ejemplo con rol secundario:

```bash
python app.py review-link --project-id licencia_conducir --link-id link_005 --primary-role terminal_case --secondary-role auxiliary_info --confidence media --notes "Puede ser tramite propio y tambien informacion auxiliar de costos"
```

Esto actualiza:

- `data/projects/licencia_conducir/human_review.json`
- `data/projects/licencia_conducir/project.json`
- `data/projects/licencia_conducir/change_log.json`

Luego se puede regenerar `review_links.html` para ver las decisiones guardadas.

## App local de revision

Para revisar y guardar decisiones desde el navegador:

```bash
python web_app.py
```

Luego abrir:

```text
http://127.0.0.1:8000/
```

Desde ahi se puede entrar al proyecto `licencia_conducir`, revisar cada link por titulo y URL, elegir rol principal, roles secundarios, confianza, notas y guardar.

Tambien se puede entrar a:

```text
http://127.0.0.1:8000/projects/licencia_conducir/resources
```

La revisión agrupada de PDF está disponible en:

```text
http://127.0.0.1:8000/projects/licencia_conducir/pdf-groups
```

La pantalla muestra siempre todos los links de cada familia. El funcionario
puede confirmar directamente que representan el mismo recurso. Al guardar, la
verificación técnica comienza en segundo plano y no bloquea la decisión.

Cada partición puede revisarse por separado para elegir uso, nombre y URL
canónica. Los archivos que no pudieron analizarse permanecen como no
verificados. Las decisiones se guardan en `pdf_group_review.json`, separadas del
análisis regenerable.

La verificación está acotada: máximo 20 MB por PDF, 20 segundos de descarga,
100 páginas y 1.000.000 de caracteres para extracción textual. Superar un
límite produce `skipped_by_policy`; no invalida la decisión del funcionario.

Si la verificación completa produce una sola partición consistente, la decisión
familiar se aplica automáticamente y no exige otro guardado. Varias particiones
requieren revisión separada. Si se usa `Verificar ahora` antes de confirmar, las
particiones quedan pendientes de decisión.

Después de verificar, la pantalla resume PDF verificados, omitidos por límites,
errores de descarga, errores de análisis, pendientes y documentos diferentes.
El detalle técnico queda cerrado cuando hay una única partición consistente ya
decidida y se abre automáticamente cuando requiere intervención.

Esa pantalla muestra los recursos internos detectados por `discover-resources`, agrupados por nodo principal y separados entre recursos utiles y descartados por regla.

Para cada recurso util se puede decidir que debe hacer la herramienta:

- `Procesar como contexto`: el contenido puede alimentar documentacion o una futura pasada LLM.
- `Mostrar solo como enlace`: el usuario debe poder acceder al link, pero no se procesa como conocimiento.
- `Descartar`: no se usara para este tramite.
- `Revisar despues`: queda pendiente de validacion.

Tambien se puede indicar si aplica solo al nodo actual o si es compartido con varios nodos.

Las decisiones se guardan en:

```text
data/projects/licencia_conducir/resource_review.json
```

La app actual guarda en:

- `data/projects/licencia_conducir/human_review.json`
- `data/projects/licencia_conducir/change_log.json`

Limitacion actual: la app permite revisar links principales, visualizar recursos internos y clasificar el uso de cada recurso util. Todavia no permite editar reglas de filtrado desde pantalla, cargar informacion complementaria ni generar un resumen final de decisiones.

Pendiente importante: si un recurso interno apunta a un link que ya existe como link principal del proyecto, la herramienta deberia detectarlo y proponer vincularlo con ese nodo existente en lugar de documentarlo otra vez.

## Descubrir recursos internos

Luego de clasificar algunos links principales desde la app local, se pueden explorar los links aceptados:

```bash
python app.py discover-resources --project-id licencia_conducir
```

Este comando toma los links cuyo rol principal fue marcado como:

- `Caso terminal`
- `Informacion auxiliar`
- `Tramite relacionado`
- `Recurso compartido`

Luego descarga cada pagina aceptada y extrae links internos relevantes, por ejemplo PDFs, agendas, formularios, normativa, articulos u otros tramites relacionados.

Genera:

```text
data/projects/licencia_conducir/node_resources.json
```

Tambien usa reglas configurables desde:

```text
data/projects/licencia_conducir/resource_filter_rules.json
```

Por defecto descarta recursos cuya URL contiene:

- `/print/pdf/node/`
- `wa.me/message/`
- `/formularios/comunicar-un-error`

Los recursos descartados no se pierden: quedan registrados dentro de `discarded_resources` con la regla y el motivo de descarte.

Esta salida todavia es preliminar. Sirve para revisar que recursos auxiliares aparecen dentro de cada nodo principal antes de construir la pantalla de revision de recursos.

## Analizar PDF auxiliares

```bash
python app.py analyze-pdfs --project-id licencia_conducir
```

Genera `data/projects/licencia_conducir/pdf_analysis.json` con las apariciones y
familias iniciales construidas por el nombre normalizado obtenido de la URL. No
descarga los PDF en esta etapa.

La descarga y comparación se ejecutan bajo demanda desde la pantalla para una
familia concreta. El botón ofrece un modo local para usar solamente archivos
presentes en `data/projects/<project_id>/pdfs/`.

## Inventariar enlaces auxiliares no documentales

```bash
python app.py analyze-auxiliary-links --project-id licencia_conducir
```

Genera `data/projects/licencia_conducir/auxiliary_link_analysis.json`.

El análisis conserva apariciones y nodos de origen, excluye documentos
descargables, detecta repeticiones exactas y equivalencias normalizadas, y
propone grupos de agendas. Para agendas intermedias puede seguir hasta cinco
redirecciones HTTP dentro de dominios permitidos. No recorre enlaces del HTML.

El inventario se visualiza en:

```text
http://127.0.0.1:8000/projects/licencia_conducir/auxiliary-links
```

La pantalla permite buscar y separar agendas, equivalencias normalizadas y URLs
exactas. Muestra nodos, uso actual, contexto, URL original, destino final y
evidencia de redirección.

Cada grupo permite:

- confirmar que representa el mismo recurso, mantenerlo separado o revisarlo
  después;
- elegir uso, alcance, URL canónica, nombre y notas;
- aplicar la decisión a todas las apariciones del grupo.

Las decisiones grupales se guardan en:

```text
data/projects/licencia_conducir/auxiliary_link_group_review.json
```

También se materializan por aparición en `resource_review.json`. La decisión
grupal reemplaza clasificaciones individuales anteriores. Si el funcionario
edita después una aparición heredada, esa edición queda marcada como excepción
explícita y no se sobrescribe al actualizar el grupo.

La pantalla `resources` permite filtrar recursos pendientes, decisiones
heredadas de grupos y decisiones individuales.
