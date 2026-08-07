# Instalación local en Home Assistant OS

Esta v0.1 está pensada para probarse como **App local** antes de publicarla en GitHub/GHCR.

1. Copiá la carpeta `local_offers/` a la carpeta de Apps locales de Home Assistant (`/addons/local_offers` en la ruta clásica; por Samba puede aparecer como `local_apps`).
2. En Home Assistant abrí **Ajustes > Apps > Instalar app** y recargá la tienda.
3. Instalá **Ofertas Locales**.
4. En **Configuración** cargá la API Vision:
   - OpenAI: `vision_api_base: https://api.openai.com/v1`
   - OpenRouter: `vision_api_base: https://openrouter.ai/api/v1`
   - `vision_api_key`: tu clave
   - `vision_model`: un modelo multimodal compatible con Chat Completions
5. Cambiá `vision_enabled` a `true`.
6. Iniciá la App y abrí su Web UI.
7. Tocá **Escanear ahora**.

La primera descarga puede tardar. Con `image_mode: full` se hace una llamada Vision por página. `quarters` multiplica las llamadas por cuatro y se reserva para catálogos difíciles de leer.

## Importante sobre Heyzine

La v0.1 ya extrae el PDF original del flipbook configurado. Cuando la tienda publique un nuevo flipbook con otro ID, hay que actualizar `heyzine_url`. La detección automática del nuevo enlace queda como siguiente módulo.
