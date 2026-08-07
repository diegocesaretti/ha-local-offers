# Ofertas Locales — Home Assistant App

App experimental para Home Assistant OS/Supervised que descarga catálogos de supermercados, detecta cambios por SHA-256, renderiza PDFs y usa un modelo multimodal compatible con OpenAI Chat Completions para extraer ofertas.

## Fuentes incluidas en v0.1

- **Almacor**: `https://almacor.com.ar/catalogo/mailing.pdf` (URL fija; se detecta cuando reemplazan el PDF).
- **Heyzine**: un flipbook configurable. La app lee `flipbookcfg`, obtiene el nombre del PDF original y prueba las rutas CDN de Heyzine.

## Funciones

- chequeo programado (12 h por defecto)
- no reprocesa PDFs ya vistos
- LLM Vision opcional
- OpenAI / OpenRouter / endpoints compatibles vía `vision_api_base`
- SQLite persistente en `/data/offers.db`
- interfaz web por Home Assistant Ingress
- `sensor.local_offers` con resumen
- evento `local_offers_catalog_updated`

> v0.1: el enlace de Heyzine debe actualizarse cuando el comercio publique un flipbook con un ID nuevo. La detección automática del nuevo post/enlace queda para la siguiente etapa.
