"""OCR in baton context ingest, against a stand-in tesseract: images, scanned PDF pages, images inside Office
files, language files from a local folder only, and Confluence pages saved by the MCP step."""

import json
import shutil
import zipfile
from pathlib import Path

import pytest
from baton import cli
from baton.context import ingest, ocr

ROOT = Path(__file__).resolve().parents[4]
FIXTURE = ROOT / "fixtures" / "sample-context"
FAKE = """#!/bin/sh
if [ "$1" = "--version" ]; then echo "tesseract 5.4.0 (stand-in)"; exit 0; fi
if [ "$1" = "--list-langs" ]; then
  echo "List of available languages in \\"$TESSDATA_PREFIX\\":"
  for f in "$TESSDATA_PREFIX"/*.traineddata; do [ -e "$f" ] && basename "$f" .traineddata; done
  exit 0
fi
echo "The late fee must be at least 5.00 when the dueDate passed."
echo
echo "Read from $(basename "$1") with $4"
"""
IMAGE = b"\x89PNG\r\n\x1a\n" + b"\0" * 4000  # bigger than the icon threshold; the stand-in never decodes it
SCANNED = "The late fee must be at least 5.00 when the dueDate passed."


@pytest.fixture
def product(tmp_path, monkeypatch):
    shutil.copytree(FIXTURE, tmp_path / "p")
    central = tmp_path / "p" / "central"
    tool = tmp_path / "bin" / "tesseract"
    tool.parent.mkdir()
    tool.write_text(FAKE)
    tool.chmod(0o755)
    monkeypatch.setenv("BATON_TESSERACT", str(tool))
    tessdata = central / "org-tessdata"
    tessdata.mkdir()
    (tessdata / "eng.traineddata").write_bytes(b"model")
    settings = central / "profile" / "context.yaml"
    settings.write_text(settings.read_text() + "ocr-tessdata: org-tessdata\n")
    (central / "docs" / "scans").mkdir(parents=True)
    return central


def context_cli(central: Path, *args: str) -> int:
    return cli.main(["context", "--central", str(central), *args])


def index(central: Path) -> dict:
    return json.loads((central / ingest.INDEX_JSON).read_text())


def source_text(central: Path, name: str) -> str:
    document = next(d for d in index(central)["documents"] if d["source"].endswith(name))
    return (central / document["file"]).read_text()


def test_an_image_is_read_by_ocr_and_marked_so(product):
    (product / "docs" / "scans" / "fee-rule.png").write_bytes(IMAGE)
    assert context_cli(product, "ingest", "--from", "docs/scans") == 0
    text = source_text(product, "fee-rule.png")
    assert "## Image text (OCR)" in text and SCANNED in text and "with eng" in text
    assert "ocr: tesseract 5.4.0 (stand-in); fee-rule.png" in text
    assert context_cli(product, "build") == 0
    drafts = (product / "profile" / "domain-drafts.md").read_text()
    assert f"quote: {SCANNED}" in drafts and "source: docs/scans/fee-rule.png#Image text (OCR)" in drafts


def test_images_inside_powerpoint_and_word_are_read_where_they_appear(product):
    deck = product / "docs" / "scans" / "deck.pptx"
    with zipfile.ZipFile(deck, "w") as archive:
        archive.writestr(
            "ppt/slides/slide1.xml",
            '<p:sld xmlns:p="x" xmlns:a="http://schemas.openxmlformats.org/'
            'drawingml/2006/main"><a:p><a:r><a:t>Fees</a:t></a:r></a:p></p:sld>',
        )
        archive.writestr(
            "ppt/slides/_rels/slide1.xml.rels",
            '<Relationships xmlns="r"><Relationship Id="rId2" Target="../media/image1.png"/></Relationships>',
        )
        archive.writestr("ppt/media/image1.png", IMAGE)
        archive.writestr("ppt/media/bullet.png", b"\x89PNG tiny")
    word = product / "docs" / "scans" / "policy.docx"
    with zipfile.ZipFile(word, "w") as archive:
        archive.writestr(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/'
            'wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Policy</w:t></w:r></w:p>'
            "</w:body></w:document>",
        )
        archive.writestr("word/media/image7.jpeg", IMAGE)
    assert context_cli(product, "ingest", "--from", "docs/scans") == 0
    slide = source_text(product, "deck.pptx")
    assert "## Slide 1: Fees\n\nImage text (OCR, image1.png): " + SCANNED in slide
    assert "bullet.png" not in slide
    assert "## Image text (OCR): image7.jpeg" in source_text(product, "policy.docx")


def test_a_scanned_pdf_page_is_read_by_ocr_and_a_typed_one_is_not(product, monkeypatch):
    (product / "docs" / "scans" / "contract.pdf").write_bytes(b"%PDF-1.4 stand-in")
    typed = "Invoices are issued on the first working day of the billing period."
    monkeypatch.setattr(ocr, "pdf_pages", lambda path: [typed, "  "])
    calls = []
    monkeypatch.setattr(ocr, "pdf_page_text", lambda path, n, langs, tessdata: calls.append(n) or SCANNED)
    assert context_cli(product, "ingest", "--from", "docs/scans") == 0
    text = source_text(product, "contract.pdf")
    assert f"## Page 1\n\n{typed}" in text and f"## Page 2 (OCR)\n\n{SCANNED}" in text
    assert calls == [2]


def test_without_a_pdf_library_a_pdf_is_listed_with_the_mirror_to_use(product, monkeypatch):
    (product / "docs" / "scans" / "contract.pdf").write_bytes(b"%PDF-1.4 stand-in")
    monkeypatch.setattr(ocr, "pdf_pages", lambda path: None)
    assert context_cli(product, "ingest", "--from", "docs/scans") == 0
    assert index(product)["skipped"] == [{"source": "docs/scans/contract.pdf", "reason": ocr.PDF_LIBRARY}]


def test_a_missing_language_file_is_reported_never_fetched(product):
    settings = product / "profile" / "context.yaml"
    settings.write_text(
        settings.read_text().replace("ocr-tessdata:", "ocr-languages: [eng, deu]\nocr-tessdata:")
    )
    (product / "docs" / "scans" / "fee-rule.png").write_bytes(IMAGE)
    assert context_cli(product, "ingest", "--from", "docs/scans") == 0
    reason = index(product)["skipped"][0]["reason"]
    assert "deu.traineddata" in reason and "org-tessdata" in reason and "mirror" in reason
    assert context_cli(product, "build") == 0 and context_cli(product, "score") == 0
    gaps = json.loads((product / "docs" / "context" / "context-map.json").read_text())["gaps"]
    assert any(g["kind"] == "document-unreadable" and "deu.traineddata" in g["text"] for g in gaps)


def test_without_tesseract_embedded_images_become_warnings_and_the_text_is_kept(
    product, monkeypatch, tmp_path
):
    monkeypatch.setenv("BATON_TESSERACT", str(tmp_path / "not-installed"))
    word = product / "docs" / "scans" / "policy.docx"
    with zipfile.ZipFile(word, "w") as archive:
        archive.writestr(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/'
            'wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>The invoice status must be OPEN.'
            "</w:t></w:r></w:p></w:body></w:document>",
        )
        archive.writestr("word/media/image1.png", IMAGE)
    assert context_cli(product, "ingest", "--from", "docs/scans") == 0
    document = index(product)["documents"][0]
    assert "The invoice status must be OPEN." in source_text(product, "policy.docx")
    assert document["warnings"][0].startswith(
        "word/media/image1.png: not read (OCR needs the tesseract binary"
    )


def test_a_confluence_page_saved_by_the_mcp_step_is_cited_by_its_url(product):
    page = product / "docs" / "legacy" / "confluence" / "SHOP" / "123-late-fees.html"
    page.parent.mkdir(parents=True)
    page.write_text(
        "<!-- confluence: https://confluence.example.org/pages/123 version 7 -->\n"
        "<h1>Late fees</h1><p>A late fee must be charged when the dueDate passed by 10 days.</p>"
    )
    assert context_cli(product, "ingest", "--from", "docs/legacy/confluence") == 0
    document = index(product)["documents"][0]
    assert document["origin"] == "https://confluence.example.org/pages/123 (version 7)"
    assert context_cli(product, "build") == 0
    drafts = (product / "profile" / "domain-drafts.md").read_text()
    assert "source: https://confluence.example.org/pages/123 (version 7)#Late fees" in drafts


def test_ocr_never_reaches_the_network():
    source = (ROOT / "tools" / "baton" / "context" / "ocr.py").read_text() + (
        ROOT / "tools" / "baton" / "context" / "ingest.py"
    ).read_text()
    for forbidden in ("urllib", "http.client", "socket", "requests", "huggingface", "download("):
        assert forbidden not in source
