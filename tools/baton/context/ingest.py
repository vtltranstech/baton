"""`baton context ingest`: unstructured documents into plain Markdown sources the miners can read.

Confluence exports (HTML), Markdown, text, Word (.docx), PowerPoint (.pptx), Excel (.xlsx), CSV/TSV and
JSON are read with the standard library; PDF only when `pypdf` is installed (`baton[pdf]`), else the file is
listed as skipped. Each document becomes `docs/context/sources/<slug>.md`: a header naming the original and
its sha256, then its headings, paragraphs and tables in order. Nothing is summarised or interpreted here; the
doc miner in `baton context build` reads these files and proposes drafts, each citing `<source>#<heading>`.
"""

from __future__ import annotations

import csv
import hashlib
import html
import io
import json
import re
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET

from baton.context import ocr

SOURCES_DIR = "docs/context/sources"
INDEX_JSON = f"{SOURCES_DIR}/index.json"
KINDS = {
    ".md": "markdown",
    ".markdown": "markdown",
    ".txt": "text",
    ".rst": "text",
    ".adoc": "text",
    ".html": "html",
    ".htm": "html",
    ".xml": "xml",
    ".docx": "docx",
    ".pptx": "pptx",
    ".xlsx": "xlsx",
    ".csv": "csv",
    ".tsv": "csv",
    ".json": "json",
    ".pdf": "pdf",
    **{suffix: "image" for suffix in ocr.IMAGE_SUFFIXES},
}
SMALLEST_IMAGE = 2_000  # bytes: smaller embedded images are icons and bullets, not text
_CONFLUENCE = re.compile(r"<!--\s*confluence:\s*(\S+)(?:\s+version\s+(\d+))?")
MAX_BYTES = 50_000_000  # per file, and per member of an Office zip
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


@dataclass
class Options:
    """OCR settings from profile/context.yaml. `reason` is set when OCR cannot run here."""

    languages: list[str] = field(default_factory=lambda: ["eng"])
    tessdata: str | None = None
    min_chars: int = 20  # a PDF page whose text layer has fewer characters is read by OCR
    embedded: bool = True  # also read the images inside Word and PowerPoint files
    reason: str | None = None

    @property
    def ocr(self) -> bool:
        return self.reason is None

    def read(self, data: bytes, suffix: str) -> str:
        return ocr.bytes_text(data, suffix, self.languages, self.tessdata)


class Unreadable(Exception):
    """The file cannot be turned into text; it is listed with the reason, never half-written."""


@dataclass
class Doc:
    blocks: list[str] = field(default_factory=list)  # Markdown blocks: "# h", paragraphs, tables
    ocr: list[str] = field(default_factory=list)  # what was read by OCR: "page 3", "word/media/image1.png"
    warnings: list[str] = field(default_factory=list)  # what was left unread, and why

    def heading(self, text: str, level: int = 2) -> None:
        text = " ".join(text.split())
        if text:
            self.blocks.append(f"{'#' * max(1, min(level, 6))} {text}")

    def para(self, text: str) -> None:
        text = " ".join(text.split())
        if text:
            self.blocks.append(text)

    def table(self, rows: list[list[str]]) -> None:
        rows = [
            [" ".join(c.split()).replace("|", "/") for c in row]
            for row in rows
            if any(c.strip() for c in row)
        ]
        if not rows:
            return
        width = max(len(r) for r in rows)
        rows = [r + [""] * (width - len(r)) for r in rows]
        lines = ["| " + " | ".join(rows[0]) + " |", "|" + " --- |" * width]
        lines += ["| " + " | ".join(r) + " |" for r in rows[1:]]
        self.blocks.append("\n".join(lines))

    def text(self) -> str:
        return "\n\n".join(self.blocks) + "\n"


# --- converters ---------------------------------------------------------------------------------------------


class _Html(HTMLParser):
    """Headings, paragraphs, list items and tables; script, style and navigation chrome are dropped."""

    _SKIP = {"script", "style", "head", "nav", "footer", "noscript", "svg"}
    _BREAK = {"p", "div", "li", "br", "tr", "section", "article", "blockquote", "pre", "dd", "dt"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.doc, self.buf, self.skip = Doc(), [], 0
        self.heading_level = 0
        self.rows: list[list[str]] | None = None
        self.cell: list[str] | None = None

    def _flush(self) -> None:
        text = "".join(self.buf)
        self.buf = []
        if self.heading_level:
            self.doc.heading(text, self.heading_level)
        else:
            self.doc.para(text)

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self.skip += 1
        elif self.skip:
            return
        elif re.fullmatch(r"h[1-6]", tag):
            self._flush()
            self.heading_level = int(tag[1])
        elif tag == "table":
            self._flush()
            self.rows = []
        elif tag == "tr" and self.rows is not None:
            self.rows.append([])
        elif tag in ("td", "th") and self.rows is not None:
            self.cell = []
        elif tag in self._BREAK and self.cell is None:
            self._flush()

    def handle_endtag(self, tag):
        if tag in self._SKIP:
            self.skip = max(0, self.skip - 1)
        elif self.skip:
            return
        elif re.fullmatch(r"h[1-6]", tag):
            self._flush()
            self.heading_level = 0
        elif tag in ("td", "th") and self.cell is not None and self.rows is not None:
            if not self.rows:
                self.rows.append([])
            self.rows[-1].append("".join(self.cell))
            self.cell = None
        elif tag == "table" and self.rows is not None:
            self.doc.table(self.rows)
            self.rows = None
        elif tag in self._BREAK and self.cell is None:
            self._flush()

    def handle_data(self, data):
        if self.skip:
            return
        (self.cell if self.cell is not None else self.buf).append(data)

    def close(self):
        super().close()
        self._flush()


def from_html(text: str) -> Doc:
    parser = _Html()
    parser.feed(text)
    parser.close()
    return parser.doc


def from_markdown(text: str) -> Doc:
    doc = Doc()
    doc.blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    return doc


def from_text(text: str) -> Doc:
    doc = Doc()
    for block in re.split(r"\n\s*\n", text):
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if len(lines) == 1 and len(lines[0]) < 80 and (lines[0].isupper() or lines[0].endswith(":")):
            doc.heading(lines[0].rstrip(":").title() if lines[0].isupper() else lines[0].rstrip(":"))
        elif lines:
            doc.para(" ".join(lines))
    return doc


def from_xml(text: str) -> Doc:
    """Generic XML (a Confluence storage-format page, for instance): its markup read as HTML."""
    return from_html(re.sub(r"<\?xml[^>]*\?>", "", text))


def _zip_member(archive: zipfile.ZipFile, name: str) -> bytes:
    info = archive.getinfo(name)
    if info.file_size > MAX_BYTES:
        raise Unreadable(f"{name} is larger than {MAX_BYTES} bytes")
    return archive.read(name)


def _xml(data: bytes) -> ET.Element:
    if b"<!DOCTYPE" in data[:2000] or b"<!ENTITY" in data[:2000]:
        raise Unreadable("an Office part declares a DTD or entities; refused")
    return ET.fromstring(data)


def _image_members(names: list[str], folder: str) -> list[str]:
    return sorted(n for n in names if n.startswith(folder) and n.lower().endswith(ocr.IMAGE_SUFFIXES))


def _read_image(archive: zipfile.ZipFile, name: str, options: Options | None, doc: Doc) -> str:
    """OCR text of one embedded image, or "" (left unread is recorded as a warning)."""
    if options is None or not options.embedded:
        return ""
    data = _zip_member(archive, name)
    if len(data) < SMALLEST_IMAGE:
        return ""
    if not options.ocr:
        doc.warnings.append(f"{name}: not read ({options.reason})")
        return ""
    try:
        text = " ".join(options.read(data, Path(name).suffix.lower()).split())
    except ocr.OcrUnavailable as exc:
        doc.warnings.append(f"{name}: {exc}")
        return ""
    if text:
        doc.ocr.append(name)
    return text


def from_docx(data: bytes, options: Options | None = None) -> Doc:
    doc = Doc()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        body = _xml(_zip_member(archive, "word/document.xml")).find(f"{_W}body")
        images = [
            (n, _read_image(archive, n, options, doc))
            for n in _image_members(archive.namelist(), "word/media/")
        ]
    for node in list(body) if body is not None else []:
        if node.tag == f"{_W}p":
            text = "".join(t.text or "" for t in node.iter(f"{_W}t"))
            style = node.find(f"{_W}pPr/{_W}pStyle")
            name = style.get(f"{_W}val", "") if style is not None else ""
            level = re.search(r"(?i)heading\s*(\d)", name)
            if level:
                doc.heading(text, int(level.group(1)))
            elif name.lower().startswith("title"):
                doc.heading(text, 1)
            else:
                doc.para(text)
        elif node.tag == f"{_W}tbl":
            doc.table(
                [
                    ["".join(t.text or "" for t in cell.iter(f"{_W}t")) for cell in row.iter(f"{_W}tc")]
                    for row in node.iter(f"{_W}tr")
                ]
            )
    for name, text in images:
        if text:
            doc.heading(f"Image text (OCR): {Path(name).name}", 2)
            doc.para(text)
    return doc


def _slide_number(name: str) -> int:
    match = re.search(r"(\d+)\.xml$", name)
    return int(match.group(1)) if match else 0


def _slide_images(archive: zipfile.ZipFile, names: list[str], number: int) -> list[str]:
    """The media files slide `number` shows, from its relationships part."""
    rels = f"ppt/slides/_rels/slide{number}.xml.rels"
    if rels not in names:
        return []
    found = []
    for rel in _xml(_zip_member(archive, rels)).iter():
        target = rel.get("Target", "")
        if "/media/" in f"/{target}" and target.lower().endswith(ocr.IMAGE_SUFFIXES):
            name = "ppt/" + target.replace("../", "")
            if name in names and name not in found:
                found.append(name)
    return found


def from_pptx(data: bytes, options: Options | None = None) -> Doc:
    doc = Doc()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        slides = sorted((n for n in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)), key=_slide_number)
        for name in slides:
            number = _slide_number(name)
            paragraphs = [
                "".join(t.text or "" for t in p.iter(f"{_A}t"))
                for p in _xml(_zip_member(archive, name)).iter(f"{_A}p")
            ]
            paragraphs = [p for p in paragraphs if p.strip()]
            title = paragraphs[0] if paragraphs else ""
            doc.heading(f"Slide {number}: {title}" if title else f"Slide {number}", 2)
            for paragraph in paragraphs[1:]:
                doc.para(paragraph)
            notes = f"ppt/notesSlides/notesSlide{number}.xml"
            if notes in names:
                text = [
                    " ".join("".join(t.text or "" for t in p.iter(f"{_A}t")).split())
                    for p in _xml(_zip_member(archive, notes)).iter(f"{_A}p")
                ]
                text = [t for t in text if t and not t.isdigit()]
                if text:
                    doc.para("Speaker notes: " + " ".join(text))
            for image in _slide_images(archive, names, number):
                text = _read_image(archive, image, options, doc)
                if text:
                    doc.para(f"Image text (OCR, {Path(image).name}): {text}")
    return doc


def from_xlsx(data: bytes) -> Doc:
    doc = Doc()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        shared: list[str] = []
        if "xl/sharedStrings.xml" in names:
            shared = [
                "".join(t.text or "" for t in si.iter(f"{_S}t"))
                for si in _xml(_zip_member(archive, "xl/sharedStrings.xml")).iter(f"{_S}si")
            ]
        titles: dict[str, str] = {}
        if "xl/workbook.xml" in names:
            for index, sheet in enumerate(
                _xml(_zip_member(archive, "xl/workbook.xml")).iter(f"{_S}sheet"), 1
            ):
                titles[f"xl/worksheets/sheet{index}.xml"] = sheet.get("name", f"Sheet {index}")
        sheets = sorted(
            (n for n in names if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n)), key=_slide_number
        )
        for name in sheets:
            doc.heading(titles.get(name, Path(name).stem), 2)
            rows = []
            for row in _xml(_zip_member(archive, name)).iter(f"{_S}row"):
                cells = []
                for cell in row.iter(f"{_S}c"):
                    value = cell.find(f"{_S}v")
                    inline = "".join(t.text or "" for t in cell.iter(f"{_S}t"))
                    text = value.text if value is not None and value.text else inline
                    if cell.get("t") == "s" and text and text.isdigit() and int(text) < len(shared):
                        text = shared[int(text)]
                    cells.append(text or "")
                rows.append(cells)
            doc.table(rows)
    return doc


def from_csv(text: str, delimiter: str) -> Doc:
    doc = Doc()
    doc.table(list(csv.reader(io.StringIO(text), delimiter=delimiter)))
    return doc


def from_json(text: str) -> Doc:
    doc = Doc()

    def walk(value, path: str) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                walk(item, f"{path}.{key}" if path else str(key))
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]")
        elif isinstance(value, str) and len(value.split()) >= 3:
            doc.heading(path, 3)
            doc.para(value)

    walk(json.loads(text), "")
    return doc


def from_pdf(path: Path, options: Options) -> Doc:
    """The text layer of each page; a page without one (a scan) is read by OCR."""
    pages = ocr.pdf_pages(path)
    if pages is None:
        raise Unreadable(ocr.PDF_LIBRARY)
    doc = Doc()
    for number, text in enumerate(pages, 1):
        if len(text.strip()) >= options.min_chars:
            doc.heading(f"Page {number}", 2)
            for block in re.split(r"\n\s*\n", text):
                doc.para(block)
            continue
        if not options.ocr:
            doc.warnings.append(f"page {number}: no text layer and not read ({options.reason})")
            continue
        try:
            scanned = ocr.pdf_page_text(path, number, options.languages, options.tessdata)
        except ocr.OcrUnavailable as exc:
            doc.warnings.append(f"page {number}: {exc}")
            continue
        doc.heading(f"Page {number} (OCR)", 2)
        doc.ocr.append(f"page {number}")
        for block in re.split(r"\n\s*\n", scanned):
            doc.para(block)
    return doc


def from_image(path: Path, options: Options) -> Doc:
    if not options.ocr:
        raise Unreadable(f"an image is read only by OCR: {options.reason}")
    try:
        text = ocr.image_text(path, options.languages, options.tessdata)
    except ocr.OcrUnavailable as exc:
        raise Unreadable(str(exc)) from exc
    doc = Doc(ocr=[path.name])
    doc.heading("Image text (OCR)", 2)
    for block in re.split(r"\n\s*\n", text):
        doc.para(block)
    return doc


def convert(path: Path, options: Options | None = None) -> tuple[str, Doc]:
    options = options or Options(reason="OCR not configured for this call")
    kind = KINDS.get(path.suffix.lower())
    if kind is None:
        raise Unreadable(f"{path.suffix or 'no extension'} is not a supported format")
    if path.stat().st_size > MAX_BYTES:
        raise Unreadable(f"larger than {MAX_BYTES} bytes")
    try:
        if kind in ("docx", "pptx", "xlsx"):
            if kind == "xlsx":
                return kind, from_xlsx(path.read_bytes())
            return kind, (from_docx if kind == "docx" else from_pptx)(path.read_bytes(), options)
        if kind == "pdf":
            return kind, from_pdf(path, options)
        if kind == "image":
            return kind, from_image(path, options)
        text = path.read_text(encoding="utf-8", errors="replace")
        if kind == "html":
            return kind, from_html(text)
        if kind == "xml":
            return kind, from_xml(text)
        if kind == "markdown":
            return kind, from_markdown(text)
        if kind == "csv":
            return kind, from_csv(text, "\t" if path.suffix.lower() == ".tsv" else ",")
        if kind == "json":
            return kind, from_json(text)
        return kind, from_text(text)
    except (zipfile.BadZipFile, KeyError, ET.ParseError, ValueError, csv.Error) as exc:
        raise Unreadable(f"{kind} could not be read: {exc}") from exc


# --- the run ------------------------------------------------------------------------------------------------


def _origin(path: Path) -> str | None:
    """The Confluence page a saved file came from, when the agent that fetched it wrote the header line
    `<!-- confluence: <page url> version <n> -->` (the /onboard skill's Confluence MCP step)."""
    if path.suffix.lower() not in (".html", ".htm", ".xml", ".md", ".markdown", ".txt"):
        return None
    with path.open("rb") as handle:
        head = handle.read(600).decode("utf-8", errors="replace")
    match = _CONFLUENCE.search(head)
    if not match:
        return None
    return match.group(1) + (f" (version {match.group(2)})" if match.group(2) else "")


def slug(rel: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", rel.replace("/", "--")).strip("-")
    return stem[:150] or "document"


def expand(central: Path, patterns: list[str]) -> list[tuple[Path, str]]:
    """(file, its name as cited) for each glob (relative to the central repo) or path given."""
    found: dict[Path, str] = {}
    for pattern in patterns:
        candidate = Path(pattern).expanduser()
        base = candidate if candidate.is_absolute() else central / pattern
        if base.is_file():
            paths = [base]
        elif base.is_dir():
            paths = sorted(p for p in base.rglob("*") if p.is_file())
        else:
            paths = sorted(p for p in central.glob(pattern) if p.is_file())
        for path in paths:
            if path.suffix.lower() not in KINDS or path.name.startswith((".", "~$")):
                continue
            resolved = path.resolve()
            try:
                name = resolved.relative_to(central.resolve()).as_posix()
            except ValueError:
                name = resolved.as_posix()
            if SOURCES_DIR in name:
                continue
            found.setdefault(resolved, name)
    return sorted(found.items(), key=lambda item: item[1])


def options_from(settings) -> Options:
    """OCR options from the context settings, with the reason OCR cannot run here when it cannot."""
    options = Options(
        list(settings.ocr_languages),
        settings.ocr_tessdata,
        settings.ocr_min_chars,
        settings.ocr_embedded_images,
    )
    options.reason = ocr.check(options.languages, options.tessdata)
    return options


def run_ingest(central: Path, patterns: list[str], options: Options | None = None) -> dict:
    options = options or Options(reason=ocr.check(["eng"]))
    out_dir = central / SOURCES_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    index_path = central / INDEX_JSON
    previous = {}
    if index_path.is_file():
        try:
            previous = {
                d["source"]: d for d in json.loads(index_path.read_text(encoding="utf-8"))["documents"]
            }
        except (ValueError, KeyError, TypeError):
            previous = {}
    documents, skipped = dict(previous), []
    written = unchanged = 0
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    for path, name in expand(central, patterns):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        old = previous.get(name)
        if old and old.get("sha256") == digest and (central / old["file"]).is_file():
            unchanged += 1
            continue
        try:
            kind, doc = convert(path, options)
        except (Unreadable, OSError) as exc:
            skipped.append({"source": name, "reason": str(exc)})
            continue
        if not doc.blocks:
            skipped.append({"source": name, "reason": "no text found"})
            continue
        target = f"{SOURCES_DIR}/{slug(name)}.md"
        origin = _origin(path)
        extra = (f"origin: {origin}\n" if origin else "") + (
            f"ocr: {ocr.version()}; {', '.join(doc.ocr)}\n" if doc.ocr else ""
        )
        header = (
            f"<!-- baton:source\nsource: {name}\nkind: {kind}\nsha256: {digest}\ningested: {now}\n"
            f"{extra}-->\n"
            f"# {html.escape(Path(name).name, quote=False)}\n\n"
        )
        (central / target).write_text(header + doc.text(), encoding="utf-8")
        documents[name] = {
            "source": name,
            "file": target,
            "kind": kind,
            "sha256": digest,
            "ingested": now,
            "sections": sum(b.startswith("#") for b in doc.blocks),
            **({"origin": origin} if origin else {}),
            **({"ocr": doc.ocr} if doc.ocr else {}),
            **({"warnings": doc.warnings} if doc.warnings else {}),
        }
        written += 1
    index = {"documents": sorted(documents.values(), key=lambda d: d["source"]), "skipped": skipped}
    index_path.write_text(json.dumps(index, indent=1) + "\n", encoding="utf-8")
    return {
        "ocr": "available" if options.ocr else options.reason,
        "warnings": {d["source"]: d["warnings"] for d in documents.values() if d.get("warnings")},
        "written": written,
        "unchanged": unchanged,
        "skipped": skipped,
        "documents": len(documents),
        "wrote": [INDEX_JSON] + ([f"{SOURCES_DIR}/*.md"] if written else []),
    }
