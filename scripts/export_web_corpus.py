"""Chunk sample_docs/ with the same settings as the app and write web/corpus.json for the in-browser demo."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import load_settings  # noqa: E402
from app.ingest import SUPPORTED, content_id, load_pages, split  # noqa: E402


def main():
    s = load_settings()
    docs, chunks = [], []
    for path in sorted(s.sample_dir.iterdir()):
        if path.suffix.lower() not in SUPPORTED:
            continue
        pages = load_pages(path, path.name)
        parts = split(pages, content_id(path.read_bytes()), s.chunk_size, s.chunk_overlap)
        docs.append({"source": path.name, "pages": len(pages) if path.suffix == ".pdf" else None, "chunks": len(parts)})
        chunks += [{"id": c.metadata["id"], "source": c.metadata["source"], "page": c.metadata["page"],
                    "text": c.page_content} for c in parts]
    out = Path(__file__).resolve().parent.parent / "web" / "corpus.json"
    out.write_text(json.dumps({"documents": docs, "chunks": chunks}, ensure_ascii=False))
    print(f"wrote {out} with {len(docs)} documents and {len(chunks)} chunks")


if __name__ == "__main__":
    main()
