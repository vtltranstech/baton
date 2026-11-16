"""OCR for `baton context ingest`: scanned PDF pages, image files and the images inside Word and PowerPoint.

The engine is Tesseract (Apache-2.0), called as its command-line program, so it needs no Python package.
Nothing is ever downloaded: the binary and its language files (`<lang>.traineddata`) must already be on the
machine, installed from the organisation's own package mirror. `BATON_TESSERACT` names the binary,
`ocr-tessdata` in profile/context.yaml (or `TESSDATA_PREFIX`) the folder of language files, and a language
with no file there is reported, never fetched. PDF pages are read and rendered with pypdfium2 (`baton[pdf]`,
from the organisation's PyPI mirror). Text that came from OCR is always marked `(OCR)` where it lands, so a
reader and the drafts that cite it know it was read from pixels, not typed.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

PDF_LIBRARY = "PDF needs pypdfium2: pipx inject baton pypdfium2 (from your organisation's PyPI mirror)"
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".webp", ".pnm", ".ppm")
TIMEOUT = 180
INSTALL = (
    "OCR needs the tesseract binary and its language files from your organisation's package mirror "
    "(tesseract / tesseract-ocr / tesseract-ocr-<lang>); BATON_TESSERACT names the binary, ocr-tessdata "
    "in profile/context.yaml the language folder. Nothing is downloaded"
)


def _env(tessdata: str | None) -> dict[str, str]:
    env = dict(os.environ)
    if tessdata:
        env["TESSDATA_PREFIX"] = str(Path(tessdata).expanduser())
    return env


def languages_installed(tessdata: str | None = None) -> set[str] | None:
    """The languages Tesseract can read here, or None when it is not installed."""
    tool = binary()
    if tool is None:
        return None
    try:
        done = subprocess.run(
            [tool, "--list-langs"], capture_output=True, text=True, timeout=30, env=_env(tessdata)
        )
    except (OSError, subprocess.SubprocessError):
        return set()
    lines = (done.stdout or "").splitlines()
    return {ln.strip() for ln in lines if ln.strip() and not ln.lower().startswith("list of")}


def check(languages: list[str], tessdata: str | None = None) -> str | None:
    """Why OCR cannot run with these languages, or None when it can."""
    have = languages_installed(tessdata)
    if have is None:
        return INSTALL
    missing = [lang for lang in languages or ["eng"] if lang not in have]
    if missing:
        where = tessdata or os.environ.get("TESSDATA_PREFIX") or "the default tessdata folder"
        return (
            f"no Tesseract language file for {', '.join(missing)} in {where}; add "
            f"{', '.join(m + '.traineddata' for m in missing)} from your organisation's mirror"
        )
    return None


class OcrUnavailable(Exception):
    """No OCR engine on this machine (or it failed): the caller records why, never guesses the text."""


def binary() -> str | None:
    named = os.environ.get("BATON_TESSERACT")
    return shutil.which(named) if named else shutil.which("tesseract")


def available() -> bool:
    return binary() is not None


def version() -> str:
    tool = binary()
    if tool is None:
        return ""
    try:
        done = subprocess.run([tool, "--version"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return "tesseract"
    first = (done.stdout or done.stderr).strip().splitlines()
    return first[0] if first else "tesseract"


def image_text(path: Path, languages: list[str], tessdata: str | None = None) -> str:
    """The text Tesseract reads in one image file."""
    tool = binary()
    if tool is None:
        raise OcrUnavailable(INSTALL)
    command = [tool, str(path), "stdout", "-l", "+".join(languages or ["eng"]), "--psm", "3"]
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=TIMEOUT, env=_env(tessdata))
    except subprocess.TimeoutExpired as exc:
        raise OcrUnavailable(f"tesseract took longer than {TIMEOUT}s on {path.name}") from exc
    except OSError as exc:
        raise OcrUnavailable(f"tesseract did not run: {exc}") from exc
    if done.returncode != 0:
        reason = (done.stderr or "").strip().splitlines()
        raise OcrUnavailable(f"tesseract failed on {path.name}: {reason[-1] if reason else done.returncode}")
    return done.stdout


def bytes_text(data: bytes, suffix: str, languages: list[str], tessdata: str | None = None) -> str:
    with tempfile.TemporaryDirectory(prefix="baton-ocr-") as folder:
        path = Path(folder) / f"image{suffix}"
        path.write_bytes(data)
        return image_text(path, languages, tessdata)


# --- PDF ---------------------------------------------------------------------------------------------------


def pdf_pages(path: Path) -> list[str] | None:
    """The text layer of each page, or None when no PDF library is installed."""
    try:
        import pypdfium2 as pdfium
    except ImportError:
        return None
    document = pdfium.PdfDocument(str(path))
    try:
        pages = []
        for index in range(len(document)):
            page = document[index]
            textpage = page.get_textpage()
            pages.append(textpage.get_text_range())
            textpage.close()
            page.close()
        return pages
    finally:
        document.close()


def _ppm(width: int, height: int, rgb: bytes) -> bytes:
    return f"P6\n{width} {height}\n255\n".encode() + rgb


def render_page(path: Path, number: int, folder: Path, dpi: int = 300) -> Path:
    """Page `number` (1-based) as a PPM image Tesseract reads, rendered with pypdfium2."""
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:
        raise OcrUnavailable(PDF_LIBRARY) from exc
    document = pdfium.PdfDocument(str(path))
    try:
        bitmap = document[number - 1].render(scale=dpi / 72, rev_byteorder=True)  # RGB order
        width, height, stride = bitmap.width, bitmap.height, bitmap.stride
        channels = stride // width if width else 3
        raw = bytes(bitmap.buffer)
        rows = []
        for y in range(height):
            row = raw[y * stride : y * stride + width * channels]
            if channels == 4:
                row = b"".join(row[i : i + 3] for i in range(0, len(row), 4))
            elif channels == 1:
                row = bytes(b for b in row for _ in range(3))
            rows.append(row)
        out = folder / f"page-{number}.ppm"
        out.write_bytes(_ppm(width, height, b"".join(rows)))
        return out
    finally:
        document.close()


def pdf_page_text(path: Path, number: int, languages: list[str], tessdata: str | None = None) -> str:
    with tempfile.TemporaryDirectory(prefix="baton-ocr-") as folder:
        return image_text(render_page(path, number, Path(folder)), languages, tessdata)
