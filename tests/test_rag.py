"""Fast offline tests: fake embeddings, no LLM, temporary storage."""
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app import rag
from app.config import load_settings
from app.index import DocumentIndex
from app.ingest import clean, split, load_pages

DOC_A = b"""# Refund policy
Customers may return any product within 30 days of delivery for a full refund.
Refunds are issued to the original payment method within 5 business days.

# Shipping
Standard shipping takes 3 to 7 business days. Express shipping costs $12 and arrives in 2 days.
"""
DOC_B = b"""Quarterly results
Revenue grew 18% year on year to $640 million, driven by subscription sales in Europe.
Operating margin expanded to 24% as hosting costs fell.
"""


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv("RAG_EMBEDDING_MODEL", "fake")
    monkeypatch.setenv("LLM_PROVIDER", "none")
    monkeypatch.setenv("RAG_SEED_SAMPLES", "0")
    monkeypatch.setenv("RAG_DATA_DIR", str(tmp_path / "store"))
    return replace(load_settings(), chunk_size=200, chunk_overlap=40)


@pytest.fixture
def index(settings):
    idx = DocumentIndex(settings)
    idx.add(DOC_A, "policies.md")
    idx.add(DOC_B, "results.txt")
    return idx


def test_clean_rejoins_hyphenated_words_and_collapses_space():
    assert clean("subscrip-\ntion   revenue\n\n\n\ngrew") == "subscription revenue\n\ngrew"


def test_chunks_keep_source_page_and_stable_ids(tmp_path):
    path = tmp_path / "a.md"
    path.write_bytes(DOC_A)
    chunks = split(load_pages(path, "a.md"), "abc", chunk_size=120, chunk_overlap=20)
    assert len(chunks) > 1
    assert all(c.metadata["source"] == "a.md" and c.metadata["page"] == 0 for c in chunks)
    assert [c.metadata["id"] for c in chunks][:2] == ["abc-00000", "abc-00001"]


def test_duplicate_upload_is_detected(index):
    again = index.add(DOC_A, "copy-of-policies.md")
    assert again["duplicate"] is True
    assert len(index.documents()) == 2


def test_keyword_retrieval_finds_the_right_document(index):
    hits = index.retrieve("How much does express shipping cost?", k=3, mode="bm25")
    assert hits[0].source == "policies.md"
    assert "Express shipping costs $12" in hits[0].text


def test_hybrid_fuses_both_rankings(index):
    hits = index.retrieve("operating margin", k=2, mode="hybrid")
    assert hits[0].source == "results.txt"
    assert hits[0].bm25_rank == 1 and hits[0].vector_rank is not None


def test_delete_removes_document_from_both_indexes(index):
    doc_id = next(d["doc_id"] for d in index.documents() if d["filename"] == "results.txt")
    assert index.delete(doc_id)
    assert all(h.source != "results.txt" for h in index.retrieve("operating margin revenue", mode="hybrid"))
    assert not index.delete(doc_id)


def test_extractive_answer_cites_passages(index):
    out = rag.answer(index, None, "How long does standard shipping take?")
    assert "3 to 7 business days" in out["answer"]
    assert any(s["cited"] for s in out["sources"])


def test_prompt_numbers_passages_with_sources(index):
    hits = index.retrieve("refund", k=2)
    prompt = rag.build_prompt("What is the refund window?", hits)
    assert prompt.startswith("Passages:\n\n[1] (")
    assert "Question: What is the refund window?" in prompt


class EchoGenerator:
    name = "echo"

    def generate(self, system, prompt):
        assert "only the numbered passages" in system
        return "Returns are accepted within 30 days [1]."


def test_answer_uses_generator_and_marks_citations(index):
    out = rag.answer(index, EchoGenerator(), "What is the refund window?")
    assert out["provider"] == "echo"
    assert out["sources"][0]["cited"] is True


def test_api_upload_ask_and_delete(settings, monkeypatch):
    from app import api
    with TestClient(api.app) as client:
        assert client.get("/health").json()["documents"] == 0
        r = client.post("/documents", files=[("files", ("policies.md", DOC_A, "text/markdown"))])
        assert r.status_code == 201 and r.json()[0]["chunks"] > 0
        bad = client.post("/documents", files=[("files", ("image.png", b"x", "image/png"))])
        assert bad.status_code == 415
        answer = client.post("/ask", json={"question": "What does express shipping cost?"}).json()
        assert "$12" in answer["answer"]
        doc_id = r.json()[0]["doc_id"]
        assert client.delete(f"/documents/{doc_id}").status_code == 204
        assert client.get("/documents").json() == []
