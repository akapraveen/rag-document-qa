"""Turn PDFs and text files into clean, overlapping chunks that remember their source and page."""
import hashlib
import re
from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

SUPPORTED = {".pdf", ".txt", ".md"}
NO_PAGE = 0  # Chroma metadata cannot hold None; 0 means "not a paged document"


def content_id(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


def clean(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)  # re-join words hyphenated across PDF line breaks
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def load_pages(path: Path, source: str) -> list[Document]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        reader = PdfReader(str(path))
        pages = [Document(page_content=clean(p.extract_text() or ""), metadata={"source": source, "page": i + 1})
                 for i, p in enumerate(reader.pages)]
    elif suffix in {".txt", ".md"}:
        text = path.read_text(encoding="utf-8", errors="replace")
        pages = [Document(page_content=clean(text), metadata={"source": source, "page": NO_PAGE})]
    else:
        raise ValueError(f"Unsupported file type {suffix!r}; use one of {sorted(SUPPORTED)}")
    return [p for p in pages if p.page_content]


def split(pages: list[Document], doc_id: str, chunk_size: int, chunk_overlap: int) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n## ", "\n### ", "\n\n", "\n", ". ", " ", ""],
    )
    chunks = splitter.split_documents(pages)
    for i, chunk in enumerate(chunks):
        chunk.metadata.update(doc_id=doc_id, chunk=i, id=f"{doc_id}-{i:05d}")
    return chunks
