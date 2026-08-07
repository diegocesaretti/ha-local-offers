# Ofertas Locales 0.3.0

## Qué hace

La App monitorea los catálogos de **Almacor** y **Supermercados Caracol**, descarga los PDFs, los analiza con LLM Vision y guarda ofertas e histórico de precios en SQLite dentro de Home Assistant.

## Caracol automático

La App consulta `https://www.supercaracol.com.ar/`, busca el enlace vigente a `heyzine.com/flip-book/...` publicado por Caracol y descarga el PDF original.

- `caracol_home_url`: web donde Caracol publica el catálogo.
- `heyzine_url`: fallback manual opcional; normalmente puede quedar vacío.

## LLM principal + respaldo

La App admite dos perfiles Vision:

- principal: `vision_api_base`, `vision_api_key`, `vision_model`
- respaldo: `vision_backup_api_base`, `vision_backup_api_key`, `vision_backup_model`

Activá el segundo con `vision_backup_enabled: true`.

El perfil principal siempre se intenta primero. Si agota sus reintentos o devuelve una respuesta inválida, la misma página/recorte se procesa con el perfil de respaldo. La página siguiente vuelve a intentar primero el principal.

La Web UI muestra métricas persistentes de uso real:

- éxitos/fallas del principal,
- éxitos/fallas del respaldo,
- cantidad de failovers,
- último proveedor usado.

El botón **Probar APIs LLM** prueba ambos perfiles pero no altera estas métricas.

## Control de carga y reintentos

Las llamadas LLM pasan por un único limitador global y nunca salen simultáneamente.

Con los defaults actuales:

- pausa normal entre llamadas: `2 s`
- reintento 1: `5 s`
- reintento 2: `10 s`
- reintento 3: `60 s`

Si el servidor devuelve `Retry-After` mayor, la App respeta el tiempo más largo. Reintentos posteriores, si se configuran más de tres, continúan 120/240 s con tope defensivo de 300 s.

## Checkpoints y reanudación

Cada página/recorte extraído correctamente se guarda inmediatamente como checkpoint persistente en `/data/checkpoints`.

Si falla el LLM, se reinicia el contenedor o Home Assistant se interrumpe durante un catálogo:

- los resultados ya correctos no se pierden,
- al próximo escaneo del mismo PDF se reutilizan,
- sólo se vuelven a enviar al LLM las páginas/recortes pendientes.

El botón **Reanalizar** (`force`) sí borra los checkpoints de extracción del catálogo para obligar una lectura completa desde cero.

## Comparar precios Almacor ↔ Caracol

La vista **Comparar precios** empareja de forma conservadora ofertas actuales usando marca, nombre y presentación.

Ejemplos normalizados:

- `2,25 L` ≈ `2250 ml` / `2250 cc`
- `1 kg` ≈ `1000 g`

Si la presentación es claramente distinta no se compara. Las promociones complejas (2x1, segunda unidad, combos) conservan su texto original para evitar interpretar mal el precio unitario.

## Histórico y detección de ofertas reales

La App conserva los catálogos anteriores y usa una observación por catálogo para construir el histórico de cada producto/presentación.

Para cada oferta actual calcula, cuando hay datos suficientes:

- mínimo histórico anterior,
- promedio de 30 días,
- promedio de 60 días,
- promedio de 90 días,
- variación porcentual contra esos promedios,
- cantidad de observaciones previas.

La UI clasifica el precio actual como:

- **Nuevo mínimo**
- **En mínimo histórico**
- **Muy buena oferta**
- **Buena oferta**
- **Precio normal**
- **Sobre el promedio**
- **Sin historial**

La vista **Histórico / oportunidades** ordena primero las mejores oportunidades y permite abrir el detalle de observaciones anteriores de cada producto.

El matching histórico usa el mismo criterio conservador de producto/presentación que la comparación entre tiendas para evitar mezclar, por ejemplo, una botella de 1,5 L con una de 2,25 L.

## SIN TACC en segunda pasada

La verificación SIN TACC ya no forma parte de la extracción inicial.

Proceso:

1. Vision extrae productos, precios, promociones y `is_food`.
2. La App consolida y guarda esa base en SQLite.
3. Sólo entonces hace una segunda pasada LLM sobre los alimentos/bebidas ya guardados, usando sus IDs de base de datos.
4. Esa segunda pasada mira la página/recorte correspondiente y completa `sin_tacc`.

Regla estricta:

- `true`: sólo evidencia visual explícita SIN TACC/libre de gluten asociada al producto.
- `false`: sólo declaración explícita de no apto/contiene gluten.
- `null`: no hay evidencia suficiente.

No se infiere aptitud por marca, ingredientes supuestos o tipo de alimento.

La segunda pasada también tiene checkpoints. Si falla, el catálogo y sus precios siguen disponibles; los productos afectados aparecen como **SIN TACC no verificado** y la App intenta completar únicamente los recortes pendientes en un próximo escaneo.

## Configuración base

- scraping: `168` horas (7 días)
- Gemini directo como perfil principal por defecto
- backup desactivado hasta cargar sus credenciales/modelo
- `image_mode: full`
- `llm_delay_seconds: 2`
- `llm_max_retries: 3`
- `llm_retry_backoff_seconds: 5`

## Home Assistant

La App publica `sensor.local_offers` y dispara `local_offers_catalog_updated` al procesar un catálogo.

> La extracción, matching e histórico son automáticos, pero en promociones complejas o diferencias importantes conviene abrir el PDF original desde la propia UI.
