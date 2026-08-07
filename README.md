# Home Assistant Local Offers

Home Assistant App para detectar catálogos de supermercados locales, descargar PDFs, analizarlos con LLM Vision y guardar ofertas en SQLite con interfaz web vía Ingress.

## Estado

Versión actual: `v0.2.0`.

Fuentes actuales:

- **Almacor** (`mailing.pdf`)
- **Supermercados Caracol**, con descubrimiento automático del Heyzine vigente desde `https://www.supercaracol.com.ar/`

## Funciones principales

- Gemini (`gemini-3.6-flash`) predeterminado.
- Scraping semanal por defecto.
- Detección de cambios por SHA-256.
- Botón para probar la API LLM.
- Rate limiting y reintentos con backoff.
- Comparación de precios Almacor ↔ Caracol por producto/presentación equivalente.
- Diferencia en pesos y porcentaje, con indicación de la tienda más barata.
- Clasificación de alimentos/bebidas y marcador **SIN TACC** sólo cuando existe evidencia explícita en el catálogo.
- Enlace al PDF/fuente original para verificar cada oferta.

También permite usar otros proveedores Vision compatibles con OpenAI Chat Completions.

## Instalación

Agregá este repositorio como repositorio de Apps/Add-ons de Home Assistant o instalalo localmente siguiendo [INSTALL_LOCAL.md](INSTALL_LOCAL.md).

> Proyecto experimental. Las promociones complejas y la condición SIN TACC deben verificarse contra el catálogo/envase original antes de tomar decisiones de compra.
