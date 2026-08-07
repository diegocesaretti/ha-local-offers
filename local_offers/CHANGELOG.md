# Changelog

## 0.3.0

- Segundo perfil LLM Vision opcional de respaldo con failover automático.
- Métricas persistentes de éxito/falla del principal y backup, cantidad de failovers y último proveedor usado.
- El botón **Probar APIs LLM** valida ambos perfiles sin alterar las métricas de uso real.
- Política de reintentos con defaults 5 s → 10 s → 60 s; respeta un `Retry-After` mayor.
- Checkpoints persistentes por página/recorte: un escaneo interrumpido continúa desde lo pendiente en vez de empezar de cero.
- `Reanalizar` limpia checkpoints de extracción para forzar una lectura completa.
- Histórico de precios por producto/presentación usando los catálogos guardados.
- Mínimo histórico, promedio 30/60/90 días, variaciones porcentuales y cantidad de observaciones.
- Clasificación de oportunidades: nuevo mínimo, mínimo histórico, muy buena, buena, normal, sobre promedio y sin historial.
- Nueva vista **Histórico / oportunidades** y detalle de observaciones anteriores.
- La comparación Almacor ↔ Caracol incorpora contexto histórico de cada precio.
- SIN TACC pasa a una segunda etapa: primero se arma la base de productos/precios; después se verifica evidencia visual sólo para alimentos ya guardados.
- La verificación SIN TACC tiene checkpoints propios y sus fallas no invalidan los precios ya extraídos.

## 0.2.0

- Heyzine pasa a identificarse correctamente como **Caracol** en la UI, base de datos y eventos.
- Descubrimiento automático del catálogo vigente desde `https://www.supercaracol.com.ar/`.
- `heyzine_url` queda como fallback manual opcional si el sitio de Caracol no expone temporalmente el enlace.
- Migración automática de registros históricos `Heyzine` → `Caracol`.
- Nuevo modo **Comparar precios** entre Almacor y Caracol.
- Matching conservador por marca, nombre y presentación; normaliza unidades como litros/ml/cc y kg/g.
- La comparación muestra diferencia en pesos, porcentaje y supermercado más barato.
- Gemini clasifica `is_food` y detecta evidencia visual `sin_tacc`.
- `sin_tacc=true` sólo se acepta si el folleto muestra explícitamente logo/texto SIN TACC o declaración inequívoca de libre de gluten; sin evidencia queda como no verificado.
- La Web UI suma filtros de alimentos y SIN TACC verificado.

## 0.1.3

- Gemini queda como proveedor predeterminado con `gemini-3.6-flash`.
- El scraping programado pasa a 168 horas (7 días) por defecto.
- Nuevo botón **Probar API LLM** en la Web UI.
- El test valida endpoint, API key, modelo y entrada multimodal sin procesar un catálogo.
- Nueva pausa configurable entre llamadas LLM (`llm_delay_seconds`, 2 s por defecto).
- Reintentos configurables para HTTP 429/500/502/503/504.
- Backoff exponencial configurable y soporte de `Retry-After`.
- La UI muestra frecuencia, delay y cantidad de reintentos configurados.

## 0.1.2

- Normaliza el endpoint de Gemini aunque se ingrese la URL base o la URL completa de `chat/completions`.
- Fuerza el endpoint canónico de compatibilidad OpenAI para Gemini.

## 0.1.1

- Normaliza automáticamente `vision_api_base` y agrega `https://` si falta.
- Valida el endpoint de Vision antes de realizar la petición.
- Registra el endpoint y modelo usados sin exponer la API key.
- `scan_on_start` pasa a `false` por defecto para un arranque más seguro.
- Permite endpoints compatibles con OpenAI como Gemini aunque Home Assistant no los valide como tipo `url`.

## 0.1.0

- Descarga directa de Almacor.
- Extracción del PDF original desde Heyzine `flipbookcfg`.
- Detección de cambios por SHA-256.
- Renderizado de PDF a JPEG.
- Extracción con LLM Vision compatible con OpenAI Chat Completions.
- SQLite persistente.
- Interfaz Ingress.
- Publicación de `sensor.local_offers` y evento de catálogo actualizado.
