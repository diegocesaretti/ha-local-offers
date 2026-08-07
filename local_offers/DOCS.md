# Ofertas Locales 0.1.3

## Instalación local

Copiá la carpeta `local_offers` dentro de `/addons/local_offers` (o el directorio equivalente de Apps locales) y recargá la tienda de Apps. Luego instalá **Ofertas Locales**.

## Configuración predeterminada

La App usa Gemini como proveedor LLM predeterminado:

- `vision_api_base`: `https://generativelanguage.googleapis.com/v1beta/openai`
- `vision_model`: `gemini-3.6-flash`
- scraping programado: cada `168` horas (7 días)
- `llm_delay_seconds`: `2`
- `llm_max_retries`: `3`
- `llm_retry_backoff_seconds`: `5`

La API key no viene configurada y `vision_enabled` permanece desactivado por seguridad hasta que cargues tu clave.

## Prueba de API LLM

La Web UI incluye **Probar API LLM**. El test hace una petición multimodal mínima con una imagen diminuta para comprobar:

1. URL/endpoint.
2. API key.
3. Modelo configurado.
4. Soporte de entrada de imagen.

No descarga ni procesa un catálogo durante esta prueba.

## Control de carga y cuotas

Las páginas se procesan de forma secuencial, nunca en paralelo.

- `llm_delay_seconds`: pausa fija entre páginas/recortes.
- `llm_max_retries`: cantidad de reintentos adicionales para HTTP 429/500/502/503/504.
- `llm_retry_backoff_seconds`: espera inicial cuando la API no envía `Retry-After`. Los reintentos usan backoff exponencial.
- Si la API devuelve `Retry-After`, la App respeta ese valor (hasta un máximo defensivo).

## Otros proveedores

### OpenAI

- `vision_api_base`: `https://api.openai.com/v1`
- `vision_model`: un modelo con entrada de imagen compatible con Chat Completions.

### OpenRouter

- `vision_api_base`: `https://openrouter.ai/api/v1`
- `vision_model`: el identificador del modelo multimodal elegido en OpenRouter.

## Modo de imagen

- `full`: una llamada Vision por página. Es el modo recomendado para empezar.
- `quarters`: divide cada página en cuatro recortes solapados. Aumenta legibilidad y cantidad de llamadas; se deduplican resultados iguales.

## Home Assistant

La App publica `sensor.local_offers` usando el proxy interno de Home Assistant y dispara `local_offers_catalog_updated` cuando termina de procesar un catálogo nuevo.

Ejemplo de automatización:

```yaml
triggers:
  - trigger: event
    event_type: local_offers_catalog_updated
actions:
  - action: notify.notify
    data:
      title: "Nuevo catálogo"
      message: >-
        {{ trigger.event.data.source }}: {{ trigger.event.data.offers }} ofertas detectadas.
```

## Limitaciones actuales

- La App no descubre todavía un **nuevo ID de Heyzine** desde Facebook/Instagram/web de la tienda; procesa el URL configurado.
- La extracción depende de la precisión del modelo Vision elegido.
- No hay aún normalización avanzada entre nombres equivalentes ni histórico de “precio habitual”.
