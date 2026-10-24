from pathlib import Path
from io import BytesIO

from docx import Document as DocxDocument
from pypdf import PdfReader

SUPPORTED_TYPES = {".pdf", ".docx", ".txt", ".md"}

def extract_text(filename: str, content: bytes) -> str:
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_TYPES:
        raise ValueError(f"Unsupported file type: {extension}")

    if extension == ".pdf":
        pdf = PdfReader(BytesIO(content))
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    elif extension == ".docx":
        document = DocxDocument(BytesIO(content))
        text = "\n".join(p.text for p in document.paragraphs)
    else:
        text = content.decode("utf-8-sig")

    text = text.strip()
    if not text:
        raise ValueError("No extractable text found. Scanned PDFs require OCR.")
    return text
