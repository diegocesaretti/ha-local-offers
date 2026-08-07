# Ofertas Locales 0.2.0

## Qué hace

La App monitorea los catálogos de **Almacor** y **Supermercados Caracol**, descarga los PDFs, los analiza con Gemini Vision y guarda las ofertas en SQLite para mostrarlas dentro de Home Assistant.

## Caracol automático

No hace falta cargar manualmente el ID de Heyzine. La App consulta:

`https://www.supercaracol.com.ar/`

y busca el enlace vigente a `heyzine.com/flip-book/...` publicado por Caracol. Luego descarga el PDF original desde Heyzine.

- `caracol_home_url`: página donde Caracol publica el catálogo.
- `heyzine_url`: fallback manual opcional. Puede quedar vacío.

## Configuración predeterminada

- `vision_api_base`: `https://generativelanguage.googleapis.com/v1beta/openai`
- `vision_model`: `gemini-3.6-flash`
- scraping programado: cada `168` horas (7 días)
- `llm_delay_seconds`: `2`
- `llm_max_retries`: `3`
- `llm_retry_backoff_seconds`: `5`

La API key no viene configurada y `vision_enabled` permanece desactivado hasta que cargues tu clave.

## Comparar precios

La Web UI incluye el modo **Comparar precios**. Empareja ofertas actuales de Almacor y Caracol usando marca, nombre y presentación.

La normalización contempla equivalencias de unidad como:

- `2,25 L` ≈ `2250 ml` / `2250 cc`
- `1 kg` ≈ `1000 g`

La comparación muestra:

- precio en Almacor,
- precio en Caracol,
- diferencia en pesos,
- diferencia porcentual,
- supermercado más barato,
- texto de promoción de cada tienda.

El matching es deliberadamente conservador: si la presentación parece diferente, no compara. En promociones complejas (2x1, segunda unidad, combos, etc.) se muestra el texto original porque el precio impreso no siempre equivale a un precio unitario comparable.

## SIN TACC

El LLM devuelve dos campos nuevos:

- `is_food`: indica si el producto es alimento o bebida.
- `sin_tacc`: evidencia de aptitud SIN TACC en el folleto.

La regla es estricta:

- `true`: sólo si se ve el logo/texto SIN TACC o declaración inequívoca de libre de gluten.
- `false`: sólo si hay declaración inequívoca de que no es apto/contiene gluten.
- `null`: no hay evidencia suficiente.

La App **no infiere** aptitud SIN TACC por marca, tipo de alimento ni conocimiento previo. En la UI un alimento sin evidencia aparece como **SIN TACC no verificado**.

Tras actualizar desde 0.1.x, usá una vez **Reanalizar** para que los catálogos actuales incorporen estos campos.

## Prueba de API LLM

La Web UI incluye **Probar API LLM**. El test hace una petición multimodal mínima para comprobar endpoint, API key, modelo y soporte de imagen sin procesar un catálogo.

## Control de carga y cuotas

Las llamadas LLM pasan por un único limitador global y nunca se ejecutan simultáneamente.

- `llm_delay_seconds`: pausa mínima entre requests.
- `llm_max_retries`: reintentos para HTTP 429/500/502/503/504.
- `llm_retry_backoff_seconds`: espera base exponencial cuando la API no devuelve `Retry-After`.

## Home Assistant

La App publica `sensor.local_offers` y dispara `local_offers_catalog_updated` al procesar un catálogo nuevo.

> La extracción y el matching son automáticos, pero ante una diferencia importante conviene abrir el PDF desde la propia tabla y verificar presentación/promoción original.
