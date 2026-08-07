from __future__ import annotations

import hashlib
import html as html_lib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import fitz
import httpx


USER_AGENT = "HA-Local-Offers/0.2 (+Home Assistant App)"


@dataclass
class DownloadedCatalog:
    source: str
    source_url: str
    external_id: str | None
    title: str | None
    pdf_path: Path
    sha256: str
    page_count: int


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_id(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", value)[:100]


async def _download_pdf(client: httpx.AsyncClient, url: str) -> bytes:
    response = await client.get(url, follow_redirects=True, timeout=60)
    response.raise_for_status()
    content = response.content
    ctype = response.headers.get("content-type", "").lower()
    if not content.startswith(b"%PDF") and "pdf" not in ctype:
        raise ValueError(f"La URL no devolvió un PDF ({ctype or 'sin content-type'}).")
    return content


async def fetch_almacor(url: str, root: Path) -> DownloadedCatalog:
    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}) as client:
        data = await _download_pdf(client, url)
    digest = sha256_bytes(data)
    folder = root / "almacor" / digest[:12]
    folder.mkdir(parents=True, exist_ok=True)
    pdf_path = folder / "catalog.pdf"
    pdf_path.write_bytes(data)
    page_count = len(fitz.open(stream=data, filetype="pdf"))
    return DownloadedCatalog("Almacor", url, None, "Almacor", pdf_path, digest, page_count)


def discover_caracol_catalog_url(html: str) -> str:
    """Find the current Heyzine flipbook linked by Supermercados Caracol.

    The Caracol home page exposes the active catalog through a banner/menu link.
    We intentionally return a canonical URL without tracking parameters so a
    Facebook fbclid change cannot look like a new catalog.
    """
    decoded = html_lib.unescape(html)
    hrefs = re.findall(r'href\s*=\s*["\']([^"\']+)["\']', decoded, flags=re.I)
    candidates: list[str] = []
    for href in hrefs:
        href = href.strip()
        if href.startswith("//"):
            href = "https:" + href
        if "heyzine.com/flip-book/" not in href.lower():
            continue
        m = re.search(r"https?://(?:www\.)?heyzine\.com/flip-book/[A-Za-z0-9_-]+\.html", href, flags=re.I)
        if m:
            candidates.append(m.group(0))
    if not candidates:
        # Fallback for unusual inline JS or unquoted markup.
        m = re.search(
            r"https?://(?:www\.)?heyzine\.com/flip-book/[A-Za-z0-9_-]+\.html",
            decoded,
            flags=re.I,
        )
        if m:
            candidates.append(m.group(0))
    if not candidates:
        raise ValueError("No se encontró un enlace de catálogo Heyzine en la web de Caracol.")
    return candidates[0]


async def discover_caracol_catalog(home_url: str) -> str:
    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}) as client:
        response = await client.get(home_url, follow_redirects=True, timeout=30)
        response.raise_for_status()
        return discover_caracol_catalog_url(response.text)


def extract_heyzine_info(html: str, source_url: str) -> dict:
    cfg_pattern = r"var\s+flipbookcfg\s*=\s*({[\s\S]+?});[\s]*(?:/\*|var)"
    cfg_match = re.search(cfg_pattern, html, re.DOTALL)
    if not cfg_match:
        cfg_match = re.search(r"var\s+flipbookcfg\s*=\s*({[\s\S]+?});", html, re.DOTALL)
    if not cfg_match:
        raise ValueError("No se encontró flipbookcfg en Heyzine.")
    cfg = cfg_match.group(1)
    pdf_match = re.search(r'"name"\s*:\s*"([^"]+\.pdf)"', cfg)
    if not pdf_match:
        raise ValueError("No se encontró el nombre del PDF en Heyzine.")
    pdf_filename = pdf_match.group(1).replace("\\/", "/")

    def grab(pattern: str) -> Optional[str]:
        m = re.search(pattern, cfg)
        return m.group(1) if m else None

    flipbook_id = grab(r'"id"\s*:\s*"([^"]+)"')
    if not flipbook_id:
        m = re.search(r"/flip-book/([a-zA-Z0-9_-]+)\.html", source_url)
        flipbook_id = m.group(1) if m else None
    title = grab(r'"title"\s*:\s*"([^"]*)"') or grab(r'"custom_name"\s*:\s*"([^"]+)"')
    title = title.replace("\\/", "/") if title else None
    cdn_base = "https://cdnc.heyzine.com"
    return {
        "id": flipbook_id,
        "title": title,
        "pdf_filename": pdf_filename,
        "pdf_urls": [
            f"{cdn_base}/flip-book/pdf/{pdf_filename}",
            f"{cdn_base}/files/uploaded/{pdf_filename}",
        ],
    }


async def _fetch_heyzine_pdf(url: str, root: Path, source_name: str, folder_name: str) -> DownloadedCatalog:
    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}) as client:
        page = await client.get(url, follow_redirects=True, timeout=30)
        page.raise_for_status()
        info = extract_heyzine_info(page.text, url)
        data: bytes | None = None
        last_error: Exception | None = None
        for pdf_url in info["pdf_urls"]:
            try:
                data = await _download_pdf(client, pdf_url)
                break
            except Exception as exc:
                last_error = exc
        if data is None:
            raise RuntimeError(f"No se pudo descargar el PDF original de Heyzine: {last_error}")

    digest = sha256_bytes(data)
    external_id = info.get("id") or digest[:12]
    folder = root / folder_name / safe_id(external_id)
    folder.mkdir(parents=True, exist_ok=True)
    pdf_path = folder / "catalog.pdf"
    pdf_path.write_bytes(data)
    page_count = len(fitz.open(stream=data, filetype="pdf"))
    return DownloadedCatalog(source_name, url, external_id, info.get("title"), pdf_path, digest, page_count)


async def fetch_heyzine(url: str, root: Path) -> DownloadedCatalog:
    """Backward-compatible direct Heyzine fetch; exposed as Caracol in v0.2+."""
    return await _fetch_heyzine_pdf(url, root, "Caracol", "caracol")


async def fetch_caracol(home_url: str, fallback_heyzine_url: str, root: Path) -> DownloadedCatalog:
    try:
        catalog_url = await discover_caracol_catalog(home_url)
    except Exception:
        if not fallback_heyzine_url:
            raise
        catalog_url = fallback_heyzine_url
    return await _fetch_heyzine_pdf(catalog_url, root, "Caracol", "caracol")
