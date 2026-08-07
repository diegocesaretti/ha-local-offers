from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import fitz
from PIL import Image


@dataclass
class RenderedImage:
    page: int
    tile: str
    path: Path


def _save_jpeg(pix: fitz.Pixmap, path: Path, quality: int) -> None:
    mode = "RGB" if pix.n < 4 else "RGBA"
    img = Image.frombytes(mode, [pix.width, pix.height], pix.samples)
    if mode == "RGBA":
        img = img.convert("RGB")
    img.save(path, "JPEG", quality=quality, optimize=True)


def render_pdf(pdf_path: Path, output_dir: Path, dpi: int, quality: int,
               max_pages: int, image_mode: str = "full") -> list[RenderedImage]:
    output_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(pdf_path)
    results: list[RenderedImage] = []
    scale = dpi / 72.0
    matrix = fitz.Matrix(scale, scale)

    for idx, page in enumerate(doc):
        if idx >= max_pages:
            break
        page_num = idx + 1
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        full_path = output_dir / f"page-{page_num:03d}.jpg"
        _save_jpeg(pix, full_path, quality)

        if image_mode == "quarters":
            with Image.open(full_path) as img:
                w, h = img.size
                overlap_x = int(w * 0.06)
                overlap_y = int(h * 0.06)
                boxes = {
                    "q1": (0, 0, w // 2 + overlap_x, h // 2 + overlap_y),
                    "q2": (w // 2 - overlap_x, 0, w, h // 2 + overlap_y),
                    "q3": (0, h // 2 - overlap_y, w // 2 + overlap_x, h),
                    "q4": (w // 2 - overlap_x, h // 2 - overlap_y, w, h),
                }
                for tile, box in boxes.items():
                    tile_path = output_dir / f"page-{page_num:03d}-{tile}.jpg"
                    img.crop(box).save(tile_path, "JPEG", quality=quality, optimize=True)
                    results.append(RenderedImage(page_num, tile, tile_path))
        else:
            results.append(RenderedImage(page_num, "full", full_path))

    return results
