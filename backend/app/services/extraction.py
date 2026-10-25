import os
from io import BytesIO
from pathlib import Path

from docx import Document as DocxDocument
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph
from pypdf import PdfReader

SUPPORTED_TYPES = {".pdf", ".docx", ".txt", ".md"}


def extract_text(
    filename: str,
    content: bytes,
    extraction_warnings: list[str] | None = None,
) -> str:
    warnings = extraction_warnings if extraction_warnings is not None else []
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_TYPES:
        raise ValueError(f"Unsupported file type: {extension}")

    if extension == ".pdf":
        pdf = PdfReader(BytesIO(content))
        pages = []
        ocr_pages = 0
        max_ocr_pages = int(os.getenv("DOCUMENT_OCR_MAX_PAGES", "20"))
        for page_number, page in enumerate(pdf.pages, start=1):
            page_text = (page.extract_text() or "").strip()
            if not page_text and _ocr_enabled():
                ocr_pages += 1
                if ocr_pages > max_ocr_pages:
                    raise ValueError(
                        f"PDF exceeds the OCR page limit ({max_ocr_pages}). Split the document or raise DOCUMENT_OCR_MAX_PAGES."
                    )
                page_text = _ocr_pdf_page(content, page_number)
            if not page_text:
                warnings.append(
                    f"PDF page {page_number} had no selectable text; "
                    + ("OCR returned no readable text." if _ocr_enabled() else "OCR is disabled.")
                )
            if page_text:
                pages.append(f"[Page {page_number}]\n{page_text}")
        text = "\n\n".join(pages)
    elif extension == ".docx":
        document = DocxDocument(BytesIO(content))
        # Walk body elements in order: `document.paragraphs` omits table cells.
        blocks = []
        table_number = 0
        for child in document.element.body.iterchildren():
            if isinstance(child, CT_P):
                paragraph = Paragraph(child, document)
                if paragraph.text.strip():
                    blocks.append(paragraph.text.strip())
            elif isinstance(child, CT_Tbl):
                table_number += 1
                table = Table(child, document)
                rows = [
                    [" ".join(cell.text.split()) for cell in row.cells]
                    for row in table.rows
                ]
                rows = [row for row in rows if any(row)]
                if rows:
                    blocks.append(f"Table {table_number}:")
                    for row_number, row in enumerate(rows, start=1):
                        cells = [
                            f"Column {column_number}: {value}"
                            for column_number, value in enumerate(row, start=1)
                            if value
                        ]
                        blocks.append(
                            f"Table {table_number}, row {row_number}: "
                            + " | ".join(cells)
                        )
        text = "\n".join(blocks)
    else:
        text = content.decode("utf-8-sig")

    text = text.strip()
    if not text:
        raise ValueError("No extractable text found. Scanned PDFs require OCR.")
    return text


def _ocr_enabled() -> bool:
    return os.getenv("DOCUMENT_OCR_ENABLED", "false").strip().casefold() in {
        "1", "true", "yes", "on",
    }


def _ocr_pdf_page(content: bytes, page_number: int) -> str:
    """OCR one text-empty page, only when explicitly enabled by configuration."""
    try:
        import pytesseract
        from pdf2image import convert_from_bytes
    except ImportError as exc:
        raise ValueError(
            "OCR is enabled but optional OCR packages are missing; install requirements-ocr.txt."
        ) from exc
    try:
        images = convert_from_bytes(
            content, first_page=page_number, last_page=page_number,
            dpi=150, fmt="png", size=2000,
        )
        return pytesseract.image_to_string(images[0]).strip() if images else ""
    except Exception as exc:
        raise ValueError(
            f"OCR failed on PDF page {page_number}; verify the OCR engine and PDF renderer are installed."
        ) from exc
