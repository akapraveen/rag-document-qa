"""Runtime settings. Every value can be overridden with an environment variable (see .env.example)."""
import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    sample_dir: Path
    collection: str
    embedding_model: str
    chunk_size: int
    chunk_overlap: int
    top_k: int
    candidates: int
    llm_provider: str
    anthropic_model: str
    ollama_model: str
    ollama_host: str
    max_upload_mb: int
    seed_samples: bool


def load_settings() -> Settings:
    env = os.getenv
    return Settings(
        data_dir=Path(env("RAG_DATA_DIR", str(ROOT / "storage"))),
        sample_dir=Path(env("RAG_SAMPLE_DIR", str(ROOT / "sample_docs"))),
        collection=env("RAG_COLLECTION", "documents"),
        embedding_model=env("RAG_EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5"),
        chunk_size=int(env("RAG_CHUNK_SIZE", "900")),
        chunk_overlap=int(env("RAG_CHUNK_OVERLAP", "150")),
        top_k=int(env("RAG_TOP_K", "5")),
        candidates=int(env("RAG_CANDIDATES", "20")),
        llm_provider=env("LLM_PROVIDER", "auto"),
        anthropic_model=env("ANTHROPIC_MODEL", "claude-opus-5"),
        ollama_model=env("OLLAMA_MODEL", "llama3.2:3b"),
        ollama_host=env("OLLAMA_HOST", "http://localhost:11434"),
        max_upload_mb=int(env("RAG_MAX_UPLOAD_MB", "25")),
        seed_samples=env("RAG_SEED_SAMPLES", "1") == "1",
    )
