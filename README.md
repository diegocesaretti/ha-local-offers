# Home Assistant Local Offers

Home Assistant App para detectar catálogos de supermercados locales, descargar PDFs, analizarlos con LLM Vision y guardar ofertas e histórico de precios en SQLite con interfaz web vía Ingress.

## Estado

Versión actual: `v0.3.1`.

Fuentes actuales:

- **Almacor** (`mailing.pdf`)
- **Supermercados Caracol**, con descubrimiento automático del Heyzine vigente desde `https://www.supercaracol.com.ar/`

## Funciones principales

- Gemini (`gemini-3.6-flash`) como perfil Vision principal predeterminado.
- Segundo perfil LLM opcional de respaldo con failover automático.
- Métricas de éxito/falla/failover por proveedor.
- Scraping semanal por defecto.
- Detección de cambios por SHA-256.
- Checkpoints persistentes por página/recorte para reanudar escaneos interrumpidos.
- Reintentos LLM 5 s → 10 s → 60 s por defecto, respetando `Retry-After` si es mayor.
- Comparación de precios Almacor ↔ Caracol por producto/presentación equivalente.
- Histórico por producto: mínimo anterior, promedios 30/60/90 días y variación porcentual.
- Vista **Histórico / oportunidades** para distinguir ofertas reales de precios normales o altos.
- Semáforo gluten posterior al scraping: **Verde Sin Gluten / Amarillo indeterminado / Rojo Con TACC**.
- Integración best-effort con el listado oficial LIALG de ANMAT/INAL; matches Vigentes fuertes se identifican como **Sin Gluten · ANMAT**.
- Lo no resuelto por ANMAT se clasifica con LLM sobre texto en lotes de hasta 50, sin reenviar imágenes.
- Checkpoint individual de la clasificación gluten y fuente/confianza visibles en la UI.
- Enlace al PDF/fuente original para verificar cada oferta.

También permite usar proveedores compatibles con OpenAI Chat Completions como Groq, OpenRouter u otros endpoints configurables.

## Instalación

Agregá este repositorio como repositorio de Apps/Add-ons de Home Assistant o instalalo localmente siguiendo [INSTALL_LOCAL.md](INSTALL_LOCAL.md).

La documentación detallada está en [local_offers/DOCS.md](local_offers/DOCS.md).

> Proyecto experimental. Para decisiones de consumo vinculadas a celiaquía, verificá siempre el rótulo/envase y la fuente oficial vigente; la clasificación LLM es orientativa.
