# Ofertas Locales — Home Assistant App

App experimental para Home Assistant OS/Supervised que descarga catálogos de supermercados, detecta cambios por SHA-256, renderiza PDFs y usa un modelo multimodal para extraer ofertas.

## Fuentes

- **Almacor**: `https://almacor.com.ar/catalogo/mailing.pdf`.
- **Supermercados Caracol**: la App consulta `https://www.supercaracol.com.ar/`, detecta automáticamente el Heyzine vigente y descarga su PDF original. `heyzine_url` queda sólo como fallback manual opcional.

## Funciones

- chequeo programado cada 7 días por defecto (`168` h)
- no reprocesa PDFs ya vistos
- Gemini `gemini-3.6-flash` como modelo Vision predeterminado
- botón **Probar API LLM** desde Ingress
- pausa configurable entre llamadas LLM
- lock global: nunca dispara dos llamadas LLM en paralelo
- reintentos para 429/5xx con `Retry-After` o backoff exponencial
- SQLite persistente en `/data/offers.db`
- interfaz web por Home Assistant Ingress
- `sensor.local_offers` con resumen
- evento `local_offers_catalog_updated`
- comparación de precios Almacor ↔ Caracol
- normalización conservadora de producto/presentación (litros/ml/cc, kg/g)
- diferencia en pesos y porcentaje, con indicación del supermercado más barato
- clasificación de alimentos y marcador **SIN TACC** sólo con evidencia visual explícita

> Tras actualizar desde una versión 0.1.x conviene ejecutar una vez **Reanalizar** para que los catálogos actuales incorporen `is_food` y `sin_tacc`.
