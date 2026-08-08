# Ofertas Locales 0.3.2

## Qué hace

La App monitorea los catálogos de **Almacor** y **Supermercados Caracol**, descarga los PDFs, los analiza con LLM Vision y guarda ofertas e histórico de precios en SQLite dentro de Home Assistant.

## Caracol automático

La App consulta `https://www.supercaracol.com.ar/`, busca el enlace vigente a `heyzine.com/flip-book/...` publicado por Caracol y descarga el PDF original.

- `caracol_home_url`: web donde Caracol publica el catálogo.
- `heyzine_url`: fallback manual opcional; normalmente puede quedar vacío.

## LLM principal + respaldo

La App admite dos perfiles compatibles con OpenAI Chat Completions:

- principal: `vision_api_base`, `vision_api_key`, `vision_model`
- respaldo: `vision_backup_api_base`, `vision_backup_api_key`, `vision_backup_model`

Activá el segundo con `vision_backup_enabled: true`. El principal se intenta primero; si agota reintentos o devuelve una respuesta inválida, esa unidad de trabajo se procesa con el backup. La siguiente vuelve a intentar primero el principal.

La Web UI muestra métricas persistentes de éxitos/fallas de ambos perfiles, cantidad de failovers y último proveedor usado. El botón **Probar APIs LLM** prueba ambos perfiles sin alterar las métricas de uso real.

## Control de carga y reintentos

Las llamadas LLM pasan por un único limitador global y nunca salen simultáneamente. Con los defaults actuales:

- pausa normal entre llamadas: `2 s`
- reintento 1: `5 s`
- reintento 2: `10 s`
- reintento 3: `60 s`

Si el servidor devuelve un `Retry-After` mayor, la App respeta el tiempo más largo.

## Checkpoints y reanudación

Cada página/recorte extraído correctamente se guarda inmediatamente como checkpoint persistente. Si el proceso se interrumpe, el siguiente escaneo del mismo PDF reutiliza lo ya procesado.

Cuando la extracción completa queda consolidada en SQLite, esos checkpoints se eliminan automáticamente. Sólo se conserva el checkpoint del catálogo incompleto más reciente de cada supermercado. **Reanalizar** fuerza una lectura completa desde cero.

## Comparar precios Almacor ↔ Caracol

La vista **Comparar precios** empareja ofertas actuales de forma conservadora usando marca, nombre y presentación. Normaliza equivalencias como `2,25 L ≈ 2250 ml/cc` y `1 kg ≈ 1000 g`. Si la presentación es claramente diferente no compara. Las promociones complejas mantienen su texto original.

## Histórico y detección de ofertas reales

La App conserva en SQLite una observación por catálogo para construir el histórico de cada producto/presentación. Calcula mínimo histórico anterior, promedios de 30/60/90 días, variaciones porcentuales y cantidad de observaciones.

La UI clasifica el precio actual como **Nuevo mínimo**, **En mínimo histórico**, **Muy buena oferta**, **Buena oferta**, **Precio normal**, **Sobre el promedio** o **Sin historial**. La vista **Histórico / oportunidades** permite abrir el detalle de observaciones anteriores.

El histórico no depende de conservar los PDFs viejos: los datos útiles quedan en SQLite aunque el archivo pesado haya sido purgado.

## Semáforo gluten: ANMAT + LLM textual

La clasificación de gluten ocurre **después** de que Vision terminó de extraer productos y precios y la base ya está guardada en SQLite. No se reenvían imágenes para esta etapa.

Estados de UI:

- **Verde — Sin Gluten**
- **Amarillo — Indeterminado**
- **Rojo — Con TACC**

### 1. ANMAT / LIALG mediante Excel completo

Con `anmat_enabled: true`, al comenzar un relevamiento la App intenta usar el botón público **Exportar a Excel** del Listado Integrado de Alimentos Libres de Gluten (LIALG) de ANMAT/INAL.

El export completo se descarga y se guarda como **una única copia local reemplazable** en `/data/anmat`. El importador acepta XLSX, XLS y CSV.

Política por defecto:

- intenta refrescar el listado al relevamiento;
- si hubo otra descarga hace menos de `anmat_refresh_hours` (12 h), la reutiliza para evitar descargas repetidas durante pruebas manuales;
- si ANMAT está temporalmente caído, sólo acepta la copia local como fuente de VERDE mientras tenga menos de `anmat_cache_days` (7 días);
- una copia más vieja no se usa para certificar un verde ANMAT.

Sólo una coincidencia fuerte, no ambigua y cuya fila tenga estado **Vigente** puede producir **Sin Gluten · ANMAT**. No encontrar un producto en el listado jamás lo convierte automáticamente en rojo.

Configuración:

- `anmat_url`: `https://listadoalg.anmat.gob.ar/Home`
- `anmat_match_threshold`: `0.82`
- `anmat_refresh_hours`: `12`
- `anmat_cache_days`: `7`
- `anmat_timeout_seconds`: `30`

### 2. LLM textual

Los alimentos que ANMAT no pudo resolver se envían al LLM **sólo como texto**, en lotes de hasta 50, por ejemplo `Marca + nombre + variante + presentación`.

El LLM responde para cada ID:

- `sin_gluten`
- `con_tacc`
- `indeterminado`
- confianza de 0 a 1

El clasificador debe preferir **indeterminado** ante dudas. Cada producto queda checkpointado individualmente mientras la clasificación está incompleta; al terminar se colapsan esos checkpoints para no ensuciar SQLite.

La App guarda además `gluten_source` (`ANMAT` o `LLM`), `gluten_confidence` y detalle técnico del match/proveedor.

> ANMAT indica que, para identificar un ALG seguro al momento de compra, deben verificarse simultáneamente el símbolo oficial en el rótulo y la presencia del producto con estado Vigente en el LIALG. El semáforo es una ayuda de búsqueda y no reemplaza revisar el envase.

## Limpieza automática de almacenamiento

Con `cleanup_enabled: true` (default), la App limpia al arrancar y después de cada escaneo.

Se eliminan automáticamente:

- todos los JPEG renderizados una vez que ya no son necesarios;
- checkpoints de catálogos completados;
- checkpoints antiguos de catálogos que ya fueron reemplazados por uno más nuevo;
- estados internos obsoletos de versiones anteriores;
- PDFs históricos que excedan la retención configurada;
- archivos temporales `.tmp` huérfanos.

Se conservan:

- `offers.db` con todo el histórico de precios;
- por defecto el **PDF más reciente de cada supermercado** (`keep_pdfs_per_source: 1`);
- el PDF/checkpoint del catálogo incompleto más reciente de cada supermercado, para poder reanudar;
- una única copia actual/cacheada del Excel ANMAT.

La API `/api/status` informa bytes usados por base de datos, PDFs, renders, checkpoints y ANMAT.

## Configuración base

- scraping: `168` horas (7 días)
- Gemini directo como perfil principal por defecto
- backup desactivado hasta cargar credenciales/modelo
- ANMAT habilitado
- `anmat_refresh_hours: 12`
- `cleanup_enabled: true`
- `keep_pdfs_per_source: 1`
- `image_mode: full`
- `llm_delay_seconds: 2`
- `llm_max_retries: 3`
- `llm_retry_backoff_seconds: 5`

## Home Assistant

La App publica `sensor.local_offers` y dispara `local_offers_catalog_updated` al procesar un catálogo.

> La extracción, matching e histórico son automáticos, pero ante promociones complejas o diferencias importantes conviene revisar la fuente original disponible.
