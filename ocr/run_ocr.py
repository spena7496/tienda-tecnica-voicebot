"""
Offline OCR step for the tienda técnica voice assistant.

Pipeline (runs ONCE, offline):
    PDF  --(pdf2image/poppler)-->  page images  --(tesseract)-->  raw text
         --(regex validation/extraction)-->  structured fields
         --> data/knowledge_base.json   (consumed by the webhook / RAG)

Document source priority:
    1. ../docs_raw/*.pdf   (drop your 3-5 real documents here)
    2. ./sample_docs/*.pdf (auto-generated datasheets, so the demo always runs)

Usage:
    python run_ocr.py            # OCR + validate + write knowledge_base.json
    python run_ocr.py --lang spa
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pytesseract
from PIL import Image
from pdf2image import convert_from_path

# Documents can be PDFs (rasterised with poppler) or images (OCR'd directly, as in class).
DOC_GLOBS = ("*.pdf", "*.png", "*.jpg", "*.jpeg", "*.tif", "*.tiff")

HERE = Path(__file__).parent
DOCS_RAW = HERE.parent / "docs_raw"
SAMPLE_DOCS = HERE / "sample_docs"
OUT_JSON = HERE.parent / "data" / "knowledge_base.json"

# --- Regex used to VALIDATE / EXTRACT fields from the OCR'd text ---
RE_REFERENCE = re.compile(r"\bTEC-\d{6}\b")                       # product reference code
RE_PRICE = re.compile(r"\b\d{1,4}[.,]\d{2}\s?€")                  # price in euros
RE_WARRANTY = re.compile(r"\b(\d{1,3})\s*meses\b", re.IGNORECASE) # warranty in months
RE_DATE = re.compile(r"\b(\d{2}/\d{2}/\d{4})\b")                  # DD/MM/YYYY


def first(pattern: re.Pattern, text: str) -> str | None:
    m = pattern.search(text)
    return m.group(0) if m else None


def extract_fields(text: str) -> dict:
    """Apply regex validation/extraction over the raw OCR text."""
    warranty_m = RE_WARRANTY.search(text)
    return {
        "referencia": first(RE_REFERENCE, text),
        "precio": first(RE_PRICE, text),
        "garantia_meses": int(warranty_m.group(1)) if warranty_m else None,
        "fecha_lanzamiento": first(RE_DATE, text),
    }


def ocr_file(path: Path, lang: str) -> str:
    """OCR a document (image->text). PDFs are rasterised with poppler; images go
    straight through Tesseract (pytesseract.image_to_string), as shown in class."""
    if path.suffix.lower() == ".pdf":
        pages = convert_from_path(str(path), dpi=200)
        return "\n".join(pytesseract.image_to_string(p, lang=lang) for p in pages).strip()
    return pytesseract.image_to_string(Image.open(path), lang=lang).strip()


def list_docs(folder: Path) -> list[Path]:
    files: list[Path] = []
    for pattern in DOC_GLOBS:
        files.extend(folder.glob(pattern))
    return sorted(files)


def pick_source_dir() -> Path:
    real = list_docs(DOCS_RAW)
    if real:
        print(f"Using {len(real)} document(s) from {DOCS_RAW}/")
        return DOCS_RAW
    print(f"No documents in {DOCS_RAW}/ -> falling back to generated {SAMPLE_DOCS}/")
    return SAMPLE_DOCS


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", default="spa", help="tesseract language (default: spa)")
    args = ap.parse_args()

    src_dir = pick_source_dir()
    docs = list_docs(src_dir)
    if not docs:
        raise SystemExit(
            "No documents (PDF/PNG/JPG) found. Generate samples with: python generate_sample_docs.py"
        )

    kb = []
    for pdf in docs:
        print(f"OCR -> {pdf.name}")
        text = ocr_file(pdf, args.lang)
        fields = extract_fields(text)
        # Validation report: which regex fields were found vs missing.
        found = [k for k, v in fields.items() if v is not None]
        missing = [k for k, v in fields.items() if v is None]
        print(f"   regex OK: {found}  |  missing: {missing or 'none'}")
        kb.append({
            "source": pdf.name,
            "title": text.splitlines()[0].strip() if text else pdf.stem,
            "fields": fields,
            "text": text,
        })

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(kb, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote {len(kb)} documents -> {OUT_JSON}")


if __name__ == "__main__":
    main()
