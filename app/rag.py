"""Retrieval-augmented answering: retrieve, build a grounded prompt, generate, and attach citations."""
import re
import time

from app.index import DocumentIndex, Hit, tokenize
from app.llm import GenerationError

NOT_FOUND = "I couldn't find that in the documents."

SYSTEM_PROMPT = f"""You answer questions using only the numbered passages from the user's documents.
- Support every factual sentence with the passage numbers it relies on, written like [1] or [2][3].
- If the passages do not contain the answer, reply exactly: "{NOT_FOUND}"
- Copy numbers, names and dates exactly as they appear in the passages. Do not add outside knowledge.
- Keep it short: at most five sentences, or a brief list when the question asks for several items."""


def label(hit: Hit) -> str:
    return f"{hit.source}, page {hit.page}" if hit.page else hit.source


def build_prompt(question: str, hits: list[Hit]) -> str:
    passages = "\n\n".join(f"[{i}] ({label(h)})\n{h.text}" for i, h in enumerate(hits, start=1))
    return f"Passages:\n\n{passages}\n\nQuestion: {question}"


def plain(text: str) -> str:
    """Strip Markdown so quoted sentences read cleanly."""
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[*`_]{1,3}", "", text)
    text = re.sub(r"\s*\|\s*", " · ", text.strip(" |"))
    return re.sub(r"\s+", " ", text).strip(" ·-#>")


def extractive_answer(question: str, hits: list[Hit], max_sentences: int = 3) -> str:
    """No-LLM fallback: the sentences that share the most terms with the question, each cited."""
    terms = set(tokenize(question))
    scored = []
    for i, hit in enumerate(hits, start=1):
        for raw in re.split(r"(?<=[.!?])\s+|\n+", hit.text):
            sentence = plain(raw)
            overlap = len(terms & set(tokenize(sentence)))
            if overlap and 25 <= len(sentence) <= 400 and not set(sentence) <= set("-·: "):
                scored.append((overlap, -i, sentence, i))
    if not scored:
        return NOT_FOUND
    best = sorted(scored, reverse=True)[:max_sentences]
    return " ".join(f"{s} [{i}]" for _, _, s, i in best)


def answer(index: DocumentIndex, generator, question: str, k: int | None = None, mode: str = "hybrid") -> dict:
    t0 = time.perf_counter()
    hits = index.retrieve(question, k=k, mode=mode)
    t1 = time.perf_counter()
    if not hits:
        text, provider = "The library is empty. Upload a PDF, TXT or MD file first.", "none"
    elif generator is None:
        text, provider = extractive_answer(question, hits), "extractive (no LLM configured)"
    else:
        try:
            text, provider = generator.generate(SYSTEM_PROMPT, build_prompt(question, hits)), generator.name
        except GenerationError as e:
            text = extractive_answer(question, hits)
            provider = f"extractive fallback ({e})"
    t2 = time.perf_counter()
    cited = {int(n) for n in re.findall(r"\[(\d+)\]", text)}
    return {
        "question": question,
        "answer": text,
        "provider": provider,
        "mode": mode,
        "sources": [{"n": i, **h.to_dict(), "label": label(h), "cited": i in cited} for i, h in enumerate(hits, 1)],
        "timings_ms": {"retrieval": round((t1 - t0) * 1000), "generation": round((t2 - t1) * 1000)},
    }
