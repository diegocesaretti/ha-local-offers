# Ofertas Locales 0.3.1

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

Cada página/recorte extraído correctamente se guarda inmediatamente como checkpoint persistente en `/data/checkpoints`. Si el proceso se interrumpe, al próximo escaneo del mismo PDF sólo se procesan las partes pendientes. **Reanalizar** sí limpia esos checkpoints para forzar una lectura completa desde cero.

## Comparar precios Almacor ↔ Caracol

La vista **Comparar precios** empareja ofertas actuales de forma conservadora usando marca, nombre y presentación. Normaliza equivalencias como `2,25 L ≈ 2250 ml/cc` y `1 kg ≈ 1000 g`. Si la presentación es claramente diferente no compara. Las promociones complejas mantienen su texto original.

## Histórico y detección de ofertas reales

La App conserva los catálogos anteriores y usa una observación por catálogo para construir el histórico de cada producto/presentación. Calcula mínimo histórico anterior, promedios de 30/60/90 días, variaciones porcentuales y cantidad de observaciones.

La UI clasifica el precio actual como **Nuevo mínimo**, **En mínimo histórico**, **Muy buena oferta**, **Buena oferta**, **Precio normal**, **Sobre el promedio** o **Sin historial**. La vista **Histórico / oportunidades** permite abrir el detalle de observaciones anteriores.

## Semáforo gluten: ANMAT + LLM textual

La clasificación de gluten ocurre **después** de que Vision terminó de extraer productos y precios y la base ya está guardada en SQLite. No se reenvían imágenes para esta etapa.

Estados de UI:

- **Verde — Sin Gluten**
- **Amarillo — Indeterminado**
- **Rojo — Con TACC**

### 1. ANMAT / LIALG

Con `anmat_enabled: true`, la App intenta consultar el buscador público del **Listado Integrado de Alimentos Libres de Gluten (LIALG)** de ANMAT/INAL.

Las consultas se agrupan por marca y se cachean durante `anmat_cache_days` (7 días por defecto). Sólo una coincidencia fuerte, no ambigua y con estado **Vigente** puede producir un verde con fuente **ANMAT**.

La automatización del buscador es deliberadamente *best-effort*: el sitio público no se trata como una API contractual. Si cambia su HTML, está caído o no hay coincidencia suficientemente precisa, el catálogo continúa y el producto pasa al clasificador LLM.

Configuración:

- `anmat_url`: `https://listadoalg.anmat.gob.ar/Home`
- `anmat_match_threshold`: `0.82`
- `anmat_cache_days`: `7`
- `anmat_delay_seconds`: `0.5`
- `anmat_timeout_seconds`: `30`

### 2. LLM textual

Los alimentos que ANMAT no pudo resolver se envían al LLM **sólo como texto**, en lotes de hasta 50, por ejemplo `Marca + nombre + variante + presentación`.

El LLM responde para cada ID:

- `sin_gluten`
- `con_tacc`
- `indeterminado`
- confianza de 0 a 1

El clasificador debe preferir **indeterminado** ante dudas. Cada producto queda checkpointado individualmente, incluso si el resultado fue amarillo, por lo que una interrupción retoma sólo los IDs pendientes.

La App guarda además `gluten_source` (`ANMAT` o `LLM`), `gluten_confidence` y detalle técnico del match/proveedor.

> Importante: ANMAT indica que, para identificar un ALG seguro al momento de compra, deben verificarse simultáneamente el símbolo oficial en el rótulo y la presencia del producto con estado Vigente en el LIALG. Por eso el semáforo de la App es una ayuda de búsqueda y no reemplaza la revisión del envase.

## Configuración base

- scraping: `168` horas (7 días)
- Gemini directo como perfil principal por defecto
- backup desactivado hasta cargar credenciales/modelo
- ANMAT habilitado
- `image_mode: full`
- `llm_delay_seconds: 2`
- `llm_max_retries: 3`
- `llm_retry_backoff_seconds: 5`

## Home Assistant

La App publica `sensor.local_offers` y dispara `local_offers_catalog_updated` al procesar un catálogo.

> La extracción, matching e histórico son automáticos, pero ante promociones complejas o diferencias importantes conviene abrir el PDF original desde la UI.
