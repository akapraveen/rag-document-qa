"""The document library: a Chroma vector store plus a BM25 keyword index, fused with reciprocal rank fusion."""
import json
import re
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import DeterministicFakeEmbedding, Embeddings
from rank_bm25 import BM25Okapi

from app.config import Settings
from app.ingest import SUPPORTED, content_id, load_pages, split

RRF_K = 60
STOPWORDS = set("""a an and are as at be but by did do does for from had has have how i if in into is it its
of on or our so than that the their them then there these they this to was were what when where which who
why will with would you your""".split())


def tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+(?:[.,][0-9]+)*", text.lower()) if t not in STOPWORDS]


class FastEmbedEmbeddings(Embeddings):
    """Local ONNX embeddings (no GPU, no API key) exposed through LangChain's Embeddings interface."""

    def __init__(self, model_name: str):
        from fastembed import TextEmbedding
        self.model = TextEmbedding(model_name=model_name)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [v.tolist() for v in self.model.embed(texts)]

    def embed_query(self, text: str) -> list[float]:
        return next(iter(self.model.query_embed(text))).tolist()


def make_embeddings(name: str) -> Embeddings:
    if name == "fake":  # deterministic hashing embedding for fast, offline tests
        return DeterministicFakeEmbedding(size=64)
    return FastEmbedEmbeddings(name)


@dataclass
class Hit:
    id: str
    text: str
    source: str
    page: int
    score: float
    vector_rank: int | None
    bm25_rank: int | None

    def to_dict(self) -> dict:
        return asdict(self)


class DocumentIndex:
    def __init__(self, settings: Settings, embeddings: Embeddings | None = None):
        self.settings = settings
        self.files_dir = settings.data_dir / "files"
        self.files_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = settings.data_dir / "documents.json"
        self.manifest: dict[str, dict] = (json.loads(self.manifest_path.read_text())
                                          if self.manifest_path.exists() else {})
        self.vectors = Chroma(
            collection_name=settings.collection,
            embedding_function=embeddings or make_embeddings(settings.embedding_model),
            persist_directory=str(settings.data_dir / "chroma"),
            collection_metadata={"hnsw:space": "cosine"},
        )
        self._lock = threading.RLock()
        self._bm25: tuple[BM25Okapi, list[Document]] | None = None

    # ---- library management -------------------------------------------------------------
    def add(self, data: bytes, filename: str) -> dict:
        suffix = Path(filename).suffix.lower()
        if suffix not in SUPPORTED:
            raise ValueError(f"Unsupported file type {suffix!r}; use PDF, TXT or MD")
        doc_id = content_id(data)
        with self._lock:
            if doc_id in self.manifest:
                return {**self.manifest[doc_id], "duplicate": True}
            path = self.files_dir / f"{doc_id}{suffix}"
            path.write_bytes(data)
            pages = load_pages(path, filename)
            if not pages:
                path.unlink(missing_ok=True)
                raise ValueError(f"No extractable text in {filename} (a scanned PDF needs OCR first)")
            chunks = split(pages, doc_id, self.settings.chunk_size, self.settings.chunk_overlap)
            self.vectors.add_documents(chunks, ids=[c.metadata["id"] for c in chunks])
            entry = {"doc_id": doc_id, "filename": filename, "pages": len(pages) if suffix == ".pdf" else None,
                     "chunks": len(chunks), "characters": sum(len(p.page_content) for p in pages),
                     "added_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            self.manifest[doc_id] = entry
            self._save()
            return {**entry, "duplicate": False}

    def delete(self, doc_id: str) -> bool:
        with self._lock:
            entry = self.manifest.pop(doc_id, None)
            if entry is None:
                return False
            self.vectors.delete(ids=[f"{doc_id}-{i:05d}" for i in range(entry["chunks"])])
            for f in self.files_dir.glob(f"{doc_id}.*"):
                f.unlink()
            self._save()
            return True

    def documents(self) -> list[dict]:
        return sorted(self.manifest.values(), key=lambda d: d["filename"].lower())

    def chunk_count(self) -> int:
        return sum(d["chunks"] for d in self.manifest.values())

    def _save(self) -> None:
        self.manifest_path.write_text(json.dumps(self.manifest, indent=1))
        self._bm25 = None

    # ---- retrieval -----------------------------------------------------------------------
    def _keyword_index(self) -> tuple[BM25Okapi, list[Document]] | None:
        if self._bm25 is None:
            got = self.vectors.get(include=["documents", "metadatas"])
            docs = [Document(page_content=t, metadata=m) for t, m in zip(got["documents"], got["metadatas"])]
            if not docs:
                return None
            self._bm25 = (BM25Okapi([tokenize(d.page_content) for d in docs]), docs)
        return self._bm25

    def retrieve(self, question: str, k: int | None = None, mode: str = "hybrid") -> list[Hit]:
        """Top-k chunks for a question. mode: 'hybrid' (default), 'vector' or 'bm25'."""
        k = k or self.settings.top_k
        n = max(self.settings.candidates, k)
        with self._lock:
            if not self.manifest:
                return []
            vector_hits: list[Document] = []
            if mode in ("hybrid", "vector"):
                vector_hits = [d for d, _ in self.vectors.similarity_search_with_score(question, k=n)]
            keyword_hits: list[Document] = []
            if mode in ("hybrid", "bm25"):
                index = self._keyword_index()
                if index:
                    bm25, docs = index
                    scores = bm25.get_scores(tokenize(question))
                    order = sorted(range(len(docs)), key=lambda i: -scores[i])[:n]
                    keyword_hits = [docs[i] for i in order if scores[i] > 0]

        fused: dict[str, dict] = {}
        for name, hits in (("vector", vector_hits), ("bm25", keyword_hits)):
            for rank, doc in enumerate(hits, start=1):
                row = fused.setdefault(doc.metadata["id"], {"doc": doc, "score": 0.0, "vector": None, "bm25": None})
                row["score"] += 1.0 / (RRF_K + rank)
                row[name] = rank
        best = sorted(fused.values(), key=lambda r: -r["score"])[:k]
        return [Hit(id=r["doc"].metadata["id"], text=r["doc"].page_content, source=r["doc"].metadata["source"],
                    page=int(r["doc"].metadata.get("page", 0)), score=round(r["score"], 5),
                    vector_rank=r["vector"], bm25_rank=r["bm25"]) for r in best]

    def seed(self, folder: Path) -> list[dict]:
        added = []
        for path in sorted(folder.iterdir()):
            if path.suffix.lower() in SUPPORTED:
                added.append(self.add(path.read_bytes(), path.name))
        return added
