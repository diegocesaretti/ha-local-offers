# Home Assistant Local Offers

Home Assistant App para detectar catálogos de supermercados locales, descargar PDFs, analizarlos con LLM Vision y guardar ofertas e histórico de precios en SQLite con interfaz web vía Ingress.

## Estado

Versión actual: `v0.3.0`.

Fuentes actuales:

- **Almacor** (`mailing.pdf`)
- **Supermercados Caracol**, con descubrimiento automático del Heyzine vigente desde `https://www.supercaracol.com.ar/`

## Funciones principales

- Gemini (`gemini-3.6-flash`) como perfil Vision principal predeterminado.
- Segundo perfil LLM Vision opcional de respaldo con failover automático.
- Métricas de éxito/falla/failover por proveedor.
- Scraping semanal por defecto.
- Detección de cambios por SHA-256.
- Checkpoints persistentes por página/recorte para reanudar escaneos interrumpidos.
- Reintentos LLM 5 s → 10 s → 60 s por defecto, respetando `Retry-After` si es mayor.
- Botón para probar ambos perfiles LLM.
- Rate limiting global: nunca salen requests Vision simultáneas.
- Comparación de precios Almacor ↔ Caracol por producto/presentación equivalente.
- Histórico por producto: mínimo anterior, promedios 30/60/90 días y variación porcentual.
- Vista **Histórico / oportunidades** para distinguir ofertas reales de precios normales o altos.
- Clasificación de alimentos/bebidas.
- Verificación **SIN TACC** en una segunda pasada, únicamente después de guardar la base de productos/precios y sólo cuando existe evidencia visual explícita.
- Checkpoints independientes para completar SIN TACC sin volver a procesar los precios.
- Enlace al PDF/fuente original para verificar cada oferta.

También permite usar proveedores Vision compatibles con OpenAI Chat Completions como OpenRouter u otros endpoints configurables.

## Instalación

Agregá este repositorio como repositorio de Apps/Add-ons de Home Assistant o instalalo localmente siguiendo [INSTALL_LOCAL.md](INSTALL_LOCAL.md).

La documentación detallada está en [local_offers/DOCS.md](local_offers/DOCS.md).

> Proyecto experimental. Las promociones complejas y la condición SIN TACC deben verificarse contra el catálogo/envase original antes de tomar decisiones de compra.
