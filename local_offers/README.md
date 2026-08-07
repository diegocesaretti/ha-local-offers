# Ofertas Locales — Home Assistant App

App experimental para Home Assistant OS/Supervised que descarga catálogos de supermercados, detecta cambios por SHA-256, renderiza PDFs y usa un modelo multimodal compatible con OpenAI Chat Completions para extraer ofertas.

## Fuentes incluidas

- **Almacor**: `https://almacor.com.ar/catalogo/mailing.pdf` (URL fija; se detecta cuando reemplazan el PDF).
- **Heyzine**: un flipbook configurable. La App lee `flipbookcfg`, obtiene el nombre del PDF original y prueba las rutas CDN de Heyzine.

## Funciones

- chequeo programado cada 7 días por defecto (`168` h)
- no reprocesa PDFs ya vistos
- Gemini `gemini-3.6-flash` como modelo Vision predeterminado
- botón **Probar API LLM** desde Ingress
- pausa configurable entre llamadas LLM
- lock global: nunca dispara dos llamadas LLM en paralelo
- reintentos para 429/5xx con `Retry-After` o backoff exponencial
- OpenAI / OpenRouter / endpoints compatibles vía `vision_api_base`
- SQLite persistente en `/data/offers.db`
- interfaz web por Home Assistant Ingress
- `sensor.local_offers` con resumen
- evento `local_offers_catalog_updated`

> El enlace de Heyzine debe actualizarse cuando el comercio publique un flipbook con un ID nuevo. La detección automática del nuevo post/enlace queda para una siguiente etapa.
