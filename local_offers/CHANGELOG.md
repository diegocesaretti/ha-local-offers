# Changelog

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
