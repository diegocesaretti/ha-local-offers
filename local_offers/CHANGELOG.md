# Changelog

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
