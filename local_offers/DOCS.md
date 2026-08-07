# Ofertas Locales 0.1.0

## Instalación local

Copiá la carpeta `local_offers` dentro de `/addons/local_offers` (o el directorio equivalente de Apps locales) y recargá la tienda de Apps. Luego instalá **Ofertas Locales**.

## Configuración mínima

1. Dejá las URLs incluidas o reemplazá la de Heyzine por el flipbook actual.
2. Elegí un endpoint compatible con `POST /chat/completions` que acepte imágenes.
3. Cargá `vision_api_key` y `vision_model`.
4. Iniciá la App y abrí su Web UI.

### OpenAI

- `vision_api_base`: `https://api.openai.com/v1`
- `vision_model`: un modelo con entrada de imagen compatible con Chat Completions.

### OpenRouter

- `vision_api_base`: `https://openrouter.ai/api/v1`
- `vision_model`: el identificador del modelo multimodal elegido en OpenRouter.

## Modo de imagen

- `full`: una llamada Vision por página. Es el modo recomendado para empezar.
- `quarters`: divide cada página en cuatro recortes solapados. Aumenta legibilidad y costo; se deduplican resultados iguales.

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

## Limitaciones de v0.1

- La App no descubre todavía un **nuevo ID de Heyzine** desde Facebook/Instagram/web de la tienda; procesa el URL configurado.
- La extracción depende de la precisión del modelo Vision elegido.
- No hay aún normalización avanzada entre nombres equivalentes ni histórico de “precio habitual”.
