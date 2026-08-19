# Herramienta de modelado de tramites

Este README describe el uso y las capacidades vigentes de la aplicación. Las
tareas activas, pausadas y futuras se mantienen únicamente en
`cerebro_agentes_grafo/07_tareas_y_roadmap.md`.

## Navegación del mapa documental

El mapa usa un selector buscable similar a un `selectInput`: al escribir parte
del nombre presenta sugerencias sin distinguir mayúsculas ni tildes. La ventana
desplegable muestra nombres completos, cantidad de recursos y scroll propio.
Esto elimina la columna lateral y deja más ancho para la documentación. Los
botones `Anterior` y `Siguiente` se conservan como navegación secundaria.

Esta carpeta alojara la herramienta asistida para que una persona no tecnica pueda construir y validar la logica de un tramite a partir de paginas web oficiales.

## Estado

Aplicacion local en desarrollo activo con:

- creación de proyectos desde la pantalla principal;
- búsqueda de enlaces desde la aplicación;
- eliminación recuperable de proyectos;
- creacion de proyectos;
- deteccion y revision de links candidatos;
- persistencia de decisiones por CLI y navegador;
- exploracion de recursos internos;
- reglas configurables de filtrado;
- revision del uso y alcance de los recursos.
- analisis deterministico y agrupacion propuesta de PDF.
- inventario deterministico de enlaces auxiliares no documentales.
- vista interna calculada de nodos, apariciones, recursos canónicos y relaciones.

La vista de estado efectivo vive en
`workflows/effective_project_state.py`. Es de solo lectura: combina los JSON del
proyecto, deriva el alcance desde las relaciones activas y no crea una nueva
fuente de verdad.

La integración visual está disponible en:

```text
http://127.0.0.1:8000/projects/licencia_conducir/effective-state
```

La pantalla muestra el impacto previsto y permite desactivar o reactivar nodos.
Las decisiones se guardan en `lifecycle_review.json`; no se eliminan evidencia,
grupos, recursos ni revisiones. Al reactivar, el estado efectivo vuelve a
incorporar las relaciones anteriores sin ejecutar el descubrimiento.

El mapa documental real está disponible en:

```text
http://127.0.0.1:8000/projects/licencia_conducir/document-map
```

Consume `resolve_effective_project_state()` mediante
`workflows/document_map.py`. Muestra los 22 nodos terminales, la documentación
específica de cada nodo y la cobertura inversa de los recursos consolidados.
La interfaz usa un selector buscable de trámites, auditoría central y cobertura
contextual en un panel derecho. Desde cada tarjeta se puede cambiar el uso de
una aparición concreta entre contexto, enlace, revisión posterior y descarte.
El cambio es una excepción local del trámite: conserva la identidad canónica y
no modifica las apariciones de otros nodos. Todavía no permite agregar recursos,
eliminarlos globalmente ni cambiar su agrupación. Cada tarjeta ofrece acceso
directo al recurso: URL canónica para los consolidados y URL efectiva para los
individuales.

## Prototipo de mapa documental

Se conserva el prototipo navegable usado para validar el concepto en:

```text
prototypes/document_graph_demo.html
```

El prototipo usa datos ilustrativos y permite validar tres recorridos de
producto: mapa general con 22 nodos, auditoría documental de un trámite y
auditoría inversa de los trámites que comparten un recurso canónico. No guarda
decisiones ni representa todavía el contrato definitivo de datos.

En `Revisar casos individuales`, los nodos desactivados continúan visibles como
referencia histórica, pero aparecen atenuados y con la etiqueta `Nodo inactivo`.
Sus recursos y decisiones no se eliminan.

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

Después de revisar los links, `Generar o actualizar documentación` ejecuta desde
la aplicación la exploración de recursos y la regeneración de los análisis de
PDF y enlaces auxiliares. También existen acciones separadas en las pantallas
de ambos análisis. Estas acciones separadas actualizan primero
`node_resources.json`, por lo que también funcionan en un proyecto que todavía
no haya ejecutado la exploración de recursos.

En la lista de proyectos, el flujo principal termina en `Ver mapa documental`.
`Revisar casos individuales` y `Ver estado efectivo` aparecen aparte como
revisión avanzada; la segunda es una vista técnica. `Eliminar proyecto` se
ubica en la esquina superior derecha de cada tarjeta y mantiene la confirmación
reforzada existente.

La regeneración es conservadora: las decisiones cuyo conjunto de apariciones
no cambió siguen vigentes. Cuando un grupo incorpora o pierde apariciones, la
decisión anterior se conserva y la interfaz pide reconfirmar solamente ese
grupo. Los enlaces auxiliares pueden filtrarse por `Solo grupos con cambios`.

La pantalla principal permite crear proyectos sin usar la consola. `Nuevo
proyecto` solicita nombre y URL, propone un identificador y valida que no exista
otro proyecto con ese ID. Después se puede ejecutar `Buscar enlaces ahora` desde
la pantalla de revisión o desde el listado de proyectos. Esta acción solo se
muestra mientras el proyecto no tenga enlaces candidatos. Una vez realizado el
descubrimiento, la acción principal pasa a ser `Revisar links`.

Volver a descubrir enlaces en un proyecto trabajado no está habilitado desde la
interfaz. Se reserva para un futuro flujo `Actualizar enlaces`, con comparación
previa y confirmación para proteger decisiones existentes.

Desde 2026-08-17 el descubrimiento incluye todos los enlaces del listado oficial
sin filtrar por categoría y recorre las páginas numéricas del mismo buscador.
La categoría se conserva en `url_category` como evidencia. El recorrido tiene
un límite de 50 páginas, deduplica por URL y registra errores parciales. La
validación pública con `Saneamiento` encontró 29 candidatos en 2 páginas.

`Eliminar proyecto` exige escribir el identificador como confirmación. La
operación es recuperable: mueve datos y salidas a
`data/deleted_projects/<id>__<fecha>/`; no los borra físicamente. La restauración
todavía no está disponible desde la interfaz.

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

Las descargas usan encabezados compatibles con navegador porque el sitio
oficial rechaza clientes automáticos genéricos. Los errores de red se muestran
con mensajes operativos; el detalle técnico permanece en `pdf_analysis.json`.

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

Para los PDF, cada caso individual incluye una sección plegable para resolver
su identidad. Permite buscar una familia existente, crear una nueva, mantener
el recurso separado o excluirlo. La incorporación puede hacerse como candidata
con verificación o como equivalencia confirmada directamente.

Estas decisiones se guardan en
`data/projects/licencia_conducir/resource_identity_review.json` y se reaplican
cuando se regenera `pdf_analysis.json`.

Al guardar una resolución de identidad, la pantalla conserva sus filtros y
posición, reabre el bloque correspondiente y muestra si la pertenencia quedó
pendiente de verificación o confirmada directamente.

- `data/projects/licencia_conducir/human_review.json`
- `data/projects/licencia_conducir/change_log.json`

Las mejoras futuras de este circuito, incluida la posible vinculación de un
recurso interno con un link principal ya existente, se registran en el catálogo
único de tareas y no en este manual de uso.

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

Desde 2026-07-31 este comando toma todos los PDF incluidos en
`node_resources.json`, aunque no tengan decisión individual. Las decisiones
confirmadas de familia o partición se materializan en `resource_review.json` y
el alcance se deriva de los nodos que apuntan al recurso canónico. Si cambia la
composición de una familia ya decidida, la interfaz exige reconfirmarla.

Antes de ejecutar los análisis, las reglas de exclusión se configuran en:

```text
http://127.0.0.1:8000/projects/licencia_conducir/resource-rules
```

La pantalla permite activar, desactivar y agregar patrones por URL o texto. Para
aplicarlos todavía se deben volver a ejecutar `discover-resources`,
`analyze-pdfs` y `analyze-auxiliary-links`.

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

Una aparición heredada que se edita individualmente queda como excepción con
`overrides_group: true`. Las ediciones posteriores conservan el grupo de origen
y la identidad canónica, y una nueva materialización del grupo no sobrescribe
la excepción. Este contrato se verifica para grupos PDF y auxiliares.

La revisión individual muestra `Volver a heredar del grupo` únicamente para
esas excepciones. La acción adopta de inmediato el uso, alcance y referencia
canónica de la última decisión grupal vigente. Se rechaza si la aparición dejó
de pertenecer al grupo o si la composición actual exige reconfirmación. El
cambio afecta solo esa aparición y queda registrado en `change_log.json`.

Los filtros se conservan al guardar una decisión y también quedan reflejados en
la URL. La pantalla restaura la búsqueda, el tipo, el estado, útiles/descartados
y la posición vertical aproximada. Los nodos sin recursos coincidentes se
ocultan completamente.
