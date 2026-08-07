# Home Assistant Local Offers

Home Assistant App para detectar nuevos catálogos de supermercados locales, descargar PDFs, analizarlos con LLM Vision y guardar ofertas en una base SQLite con interfaz web vía Ingress.

## Estado

Versión inicial: `v0.1.0`.

Incluye fuentes para:

- Almacor (`mailing.pdf`)
- Catálogos Heyzine

La App evita reprocesar un catálogo cuando el hash SHA-256 no cambió y permite usar proveedores Vision compatibles con OpenAI Chat Completions.

## Instalación

Agregá este repositorio como repositorio de Apps/Add-ons de Home Assistant o instalalo localmente siguiendo [INSTALL_LOCAL.md](INSTALL_LOCAL.md).

> Proyecto experimental. Verificá las ofertas contra el catálogo original antes de tomar decisiones de compra.
