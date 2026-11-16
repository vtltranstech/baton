"""baton context ingest and the doc miner: documents into sources, drafts and the document map."""

import json
import shutil
import zipfile
from pathlib import Path

import pytest
from baton import cli
from baton.context import ingest

ROOT = Path(__file__).resolve().parents[4]
FIXTURE = ROOT / "fixtures" / "sample-context"
W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
A = 'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'
S = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'


@pytest.fixture
def product(tmp_path):
    shutil.copytree(FIXTURE, tmp_path / "p")
    return tmp_path / "p" / "central"


def context_cli(central: Path, *args: str) -> int:
    return cli.main(["context", "--central", str(central), *args])


def office(path: Path, parts: dict[str, str]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, text in parts.items():
            archive.writestr(name, text)
    return path


def docx(path: Path) -> Path:
    para = '<w:p><w:pPr><w:pStyle w:val="{style}"/></w:pPr><w:r><w:t>{text}</w:t></w:r></w:p>'
    body = (
        para.format(style="Heading1", text="Billing rules")
        + para.format(style="Normal", text="A Billing Cycle is the month an invoice covers.")
        + para.format(style="Normal", text="An invoice status must never go back from PAID to OPEN.")
        + "<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Term</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Definition"
        "</w:t></w:r></w:p></w:tc></w:tr><w:tr><w:tc><w:p><w:r><w:t>Dunning</w:t></w:r></w:p></w:tc><w:tc>"
        "<w:p><w:r><w:t>Chasing an unpaid invoice</w:t></w:r></w:p></w:tc></w:tr></w:tbl>"
    )
    return office(path, {"word/document.xml": f"<w:document {W}><w:body>{body}</w:body></w:document>"})


def pptx(path: Path) -> Path:
    def slide(*texts):
        paras = "".join(f"<a:p><a:r><a:t>{t}</a:t></a:r></a:p>" for t in texts)
        return f'<p:sld xmlns:p="x" {A}><p:txBody>{paras}</p:txBody></p:sld>'

    return office(
        path,
        {
            "ppt/slides/slide1.xml": slide("Reminder policy", "Reminders stop after the third one."),
            "ppt/slides/slide2.xml": slide("Limits", "The credit limit must not exceed 10000 per customer."),
            "ppt/notesSlides/notesSlide2.xml": slide("Agreed with the PO in October.", "2"),
        },
    )


def xlsx(path: Path) -> Path:
    return office(
        path,
        {
            "xl/workbook.xml": f'<workbook {S}><sheets><sheet name="Lineage"/></sheets></workbook>',
            "xl/sharedStrings.xml": f"<sst {S}><si><t>field</t></si><si><t>meaning</t></si>"
            f"<si><t>dueDate</t></si><si><t>Date the invoice must be paid by</t></si></sst>",
            "xl/worksheets/sheet1.xml": f"<worksheet {S}><sheetData>"
            f'<row><c t="s"><v>0</v></c><c t="s"><v>1</v></c></row>'
            f'<row><c t="s"><v>2</v></c><c t="s"><v>3</v></c></row>'
            f"</sheetData></worksheet>",
        },
    )


def test_each_format_becomes_markdown_with_its_headings_and_tables(tmp_path):
    kind, doc = ingest.convert(docx(tmp_path / "rules.docx"))
    assert kind == "docx" and doc.blocks[0] == "# Billing rules"
    assert "| Dunning | Chasing an unpaid invoice |" in doc.text()
    kind, doc = ingest.convert(pptx(tmp_path / "deck.pptx"))
    assert doc.blocks[:2] == ["## Slide 1: Reminder policy", "Reminders stop after the third one."]
    assert (
        "Speaker notes: Agreed with the PO in October." in doc.text() and "Speaker notes: 2" not in doc.text()
    )
    kind, doc = ingest.convert(xlsx(tmp_path / "lineage.xlsx"))
    assert doc.blocks[0] == "## Lineage" and "| dueDate | Date the invoice must be paid by |" in doc.text()
    _, doc = ingest.convert(FIXTURE / "central" / "docs" / "legacy" / "pricing-rules.html")
    text = doc.text()
    assert (
        "## Glossary" in text
        and "Home / Shop" not in text
        and "var x" not in text
        and "color: red" not in text
    )
    (tmp_path / "a.csv").write_text("term,definition\nTier,Discount band\n")
    assert "| Tier | Discount band |" in ingest.convert(tmp_path / "a.csv")[1].text()


def test_unreadable_and_unsupported_files_are_listed_never_half_written(product, tmp_path, monkeypatch):
    monkeypatch.setenv("BATON_TESSERACT", str(tmp_path / "no-such-tesseract"))
    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "broken.docx").write_bytes(b"not a zip")
    (tmp_path / "in" / "entities.docx").write_bytes(
        office(tmp_path / "e.docx", {"word/document.xml": '<!DOCTYPE x [<!ENTITY a "b">]><x/>'}).read_bytes()
    )
    (tmp_path / "in" / "picture.png").write_bytes(b"\x89PNG")
    (tmp_path / "in" / "movie.mp4").write_bytes(b"\0")
    assert context_cli(product, "ingest", "--from", str(tmp_path / "in")) == 0
    index = json.loads((product / ingest.INDEX_JSON).read_text())
    assert index["documents"] == []
    reasons = {s["source"].rsplit("/", 1)[-1]: s["reason"] for s in index["skipped"]}
    assert sorted(reasons) == ["broken.docx", "entities.docx", "picture.png"]
    assert "read only by OCR" in reasons["picture.png"] and "Nothing is downloaded" in reasons["picture.png"]


def test_ingest_is_incremental_and_needs_a_source(product, tmp_path):
    (product / "profile" / "context.yaml").write_text("profile-max-age-days: 36500\n")
    assert context_cli(product, "ingest") == 2
    assert context_cli(product, "ingest", "--from", "docs/legacy") == 0
    first = json.loads((product / ingest.INDEX_JSON).read_text())
    assert [d["source"] for d in first["documents"]] == [
        "docs/legacy/notes.txt",
        "docs/legacy/pricing-rules.html",
    ]
    summary = ingest.run_ingest(product, ["docs/legacy"])
    assert (summary["written"], summary["unchanged"]) == (0, 2)


def test_documents_become_drafts_with_their_source_and_a_document_map(product, tmp_path):
    docx(product / "docs" / "legacy" / "billing.docx")
    pptx(product / "docs" / "legacy" / "deck.pptx")
    assert context_cli(product, "ingest") == 0  # doc-sources in the fixture's context.yaml
    assert context_cli(product, "build") == 0 and context_cli(product, "score") == 0
    drafts = (product / "profile" / "domain-drafts.md").read_text()
    assert "### W-draft-001 - Grace Period" in drafts or "- Grace Period\ndefinition: Days after" in drafts
    assert "source: docs/legacy/pricing-rules.html#Glossary" in drafts
    assert "Wholesale Order\ndefinition: An order placed by a reseller account" in drafts
    assert "Orders shipped to the EU must carry a surcharge when the regionCode starts with EU." in drafts
    assert "source: docs/legacy/billing.docx#Billing rules" in drafts
    assert "Billing Cycle\ndefinition: the month an invoice covers." in drafts
    assert "Dunning\ndefinition: Chasing an unpaid invoice" in drafts
    assert "The credit limit must not exceed 10000 per customer." in drafts
    assert "Invoice\ndefinition" not in drafts  # already defined and confirmed in domain.md
    assert "Nice to have" not in drafts and "a must rule that is not" not in drafts
    data = json.loads((product / "docs" / "context" / "context-map.json").read_text())
    by_source = {d["source"]: d for d in data["documents"]}
    assert by_source["docs/legacy/pricing-rules.html"]["modules"] == ["shop-service/pricing"]
    assert data["byModule"]["shop-service/pricing"]["documents"] == ["docs/legacy/pricing-rules.html"]
    module_map = (product / "docs" / "context" / "modules" / "shop-service--pricing.md").read_text()
    assert "## Documents that mention it\n\n- docs/legacy/pricing-rules.html" in module_map
    assert "bp-0010" in module_map and "-> R5" in module_map
    assert "## Documents" in (product / "docs" / "context" / "context-map.md").read_text()


def test_a_confirmed_document_draft_survives_a_rebuild(product):
    assert context_cli(product, "ingest") == 0 and context_cli(product, "build") == 0
    drafts = product / "profile" / "domain-drafts.md"
    text = drafts.read_text()
    start = text.index("- Grace Period\ndefinition:")
    end = text.index("confirmed: false", start)
    drafts.write_text(text[:end] + "confirmed: true" + text[end + len("confirmed: false") :])
    assert context_cli(product, "build") == 0
    after = drafts.read_text()
    assert after.count("quote: Grace Period") == 1
    assert (
        "quote: Grace Period"
        in after.split("## Confirmed, waiting to move into domain.md")[1].split("\n## ")[0]
    )


def test_the_story_manifest_names_the_documents_about_its_scope(product):
    assert (
        context_cli(product, "ingest") == 0
        and context_cli(product, "build") == 0
        and context_cli(product, "score") == 0
    )
    context_cli(product, "check", "S-001")
    manifest = (product / "docs" / "design" / "F-001" / "S-001-context.md").read_text()
    assert "- document: docs/context/sources/docs--legacy--pricing-rules.html.md" in manifest
