"""Read CV text from .txt/.md/.pdf/.docx."""
from __future__ import annotations
from pathlib import Path


class CVReadError(Exception): ...


def read_cv(path: str | Path) -> str:
    p = Path(path)
    if not p.exists():
        raise CVReadError(f"file not found: {p}")
    ext = p.suffix.lower()
    if ext in (".txt", ".md"):
        return p.read_text(encoding="utf-8", errors="replace")
    if ext == ".pdf":
        from pypdf import PdfReader
        text = "\n".join((pg.extract_text() or "") for pg in PdfReader(str(p)).pages)
    elif ext == ".docx":
        from docx import Document
        text = "\n".join(par.text for par in Document(str(p)).paragraphs)
    else:
        raise CVReadError(f"unsupported file type {ext}; use .pdf, .docx, .txt or .md")
    if not text.strip():
        raise CVReadError("no text found in the file (scanned PDF?). Paste the text into a .txt file instead.")
    return text
