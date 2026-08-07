# Home Assistant Local Offers

Home Assistant App para detectar nuevos catálogos de supermercados locales, descargar PDFs, analizarlos con LLM Vision y guardar ofertas en una base SQLite con interfaz web vía Ingress.

## Estado

Versión actual: `v0.1.3`.

Incluye fuentes para:

- Almacor (`mailing.pdf`)
- Catálogos Heyzine

Gemini (`gemini-3.6-flash`) es el proveedor/modelo predeterminado. La App incluye prueba de API LLM desde la Web UI, scraping semanal por defecto, rate limiting configurable, reintentos con backoff y detección de cambios por SHA-256 para no reprocesar catálogos sin cambios.

También permite usar otros proveedores Vision compatibles con OpenAI Chat Completions.

## Instalación

Agregá este repositorio como repositorio de Apps/Add-ons de Home Assistant o instalalo localmente siguiendo [INSTALL_LOCAL.md](INSTALL_LOCAL.md).

> Proyecto experimental. Verificá las ofertas contra el catálogo original antes de tomar decisiones de compra.
