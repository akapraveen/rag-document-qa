"""FastAPI backend: upload documents, manage the library, and ask questions.

Run:  uvicorn app.api:app --reload      (docs at http://localhost:8000/docs)
"""
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app import rag
from app.config import load_settings
from app.index import DocumentIndex
from app.ingest import SUPPORTED
from app.llm import pick_generator

state: dict = {}


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = load_settings()
    index = DocumentIndex(settings)
    if settings.seed_samples and not index.documents() and settings.sample_dir.exists():
        index.seed(settings.sample_dir)
    state.update(settings=settings, index=index, generator=pick_generator(settings))
    yield
    state.clear()


app = FastAPI(title="RAG Document Q&A", version="1.0.0", lifespan=lifespan,
              description="Upload PDFs or text files and ask questions answered only from them, with citations.")


class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=12)
    mode: Literal["hybrid", "vector", "bm25"] = "hybrid"


class SearchRequest(AskRequest):
    pass


@app.get("/health")
def health():
    gen = state["generator"]
    return {"status": "ok", "llm": gen.name if gen else "extractive (no LLM configured)",
            "documents": len(state["index"].documents()), "chunks": state["index"].chunk_count()}


@app.get("/documents")
def list_documents():
    return state["index"].documents()


@app.post("/documents", status_code=201)
async def upload(files: list[UploadFile] = File(...)):
    limit = state["settings"].max_upload_mb * 1024 * 1024
    results = []
    for f in files:
        name = f.filename or "upload"
        if not any(name.lower().endswith(s) for s in SUPPORTED):
            raise HTTPException(415, f"{name}: only PDF, TXT and MD files are supported")
        data = await f.read()
        if len(data) > limit:
            raise HTTPException(413, f"{name}: larger than {state['settings'].max_upload_mb} MB")
        try:
            results.append(state["index"].add(data, name))
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
    return results


@app.delete("/documents/{doc_id}", status_code=204)
def delete_document(doc_id: str):
    if not state["index"].delete(doc_id):
        raise HTTPException(404, "No document with that id")


@app.post("/search")
def search(req: SearchRequest):
    return [h.to_dict() for h in state["index"].retrieve(req.question, k=req.top_k, mode=req.mode)]


@app.post("/ask")
def ask(req: AskRequest):
    return rag.answer(state["index"], state["generator"], req.question, k=req.top_k, mode=req.mode)
