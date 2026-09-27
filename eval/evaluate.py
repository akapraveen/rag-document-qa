"""Evaluate retrieval (and optionally answers) on the sample corpus.

    python -m eval.evaluate              # retrieval only: hit@1/3/5 and MRR for vector, BM25 and hybrid
    python -m eval.evaluate --answers    # also generate answers with the configured LLM and check facts
"""
import argparse
import json
import tempfile
import time
from dataclasses import replace
from pathlib import Path

from app import rag
from app.config import load_settings
from app.index import DocumentIndex
from app.llm import pick_generator

HERE = Path(__file__).parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--answers", action="store_true", help="also generate and fact-check answers")
    args = parser.parse_args()

    questions = [json.loads(line) for line in (HERE / "questions.jsonl").read_text().splitlines() if line.strip()]
    settings = replace(load_settings(), data_dir=Path(tempfile.mkdtemp(prefix="rag-eval-")))
    index = DocumentIndex(settings)
    index.seed(settings.sample_dir)
    print(f"{len(index.documents())} documents, {index.chunk_count()} chunks, {len(questions)} questions\n")

    results = {"corpus": {"documents": len(index.documents()), "chunks": index.chunk_count(),
                          "questions": len(questions), "embedding_model": settings.embedding_model},
               "retrieval": {}}
    for mode in ("vector", "bm25", "hybrid"):
        ranks = []
        for item in questions:
            hits = index.retrieve(item["q"], k=5, mode=mode)
            rank = next((i for i, h in enumerate(hits, 1) if h.source in item["sources"]), None)
            ranks.append(rank)
        results["retrieval"][mode] = {
            "hit@1": round(sum(r == 1 for r in ranks) / len(ranks), 3),
            "hit@3": round(sum(r is not None and r <= 3 for r in ranks) / len(ranks), 3),
            "hit@5": round(sum(r is not None for r in ranks) / len(ranks), 3),
            "mrr": round(sum(1 / r for r in ranks if r) / len(ranks), 3),
        }

    print("| Retrieval | hit@1 | hit@3 | hit@5 | MRR |\n|---|---|---|---|---|")
    for mode, m in results["retrieval"].items():
        print(f"| {mode} | {m['hit@1']:.2f} | {m['hit@3']:.2f} | {m['hit@5']:.2f} | {m['mrr']:.3f} |")

    if args.answers:
        generator = pick_generator(settings)
        rows, start = [], time.perf_counter()
        for item in questions:
            out = rag.answer(index, generator, item["q"])
            ok = item["expect"].lower() in out["answer"].lower()
            rows.append({"q": item["q"], "expect": item["expect"], "correct": ok, "answer": out["answer"]})
            print(f"{'PASS' if ok else 'MISS'}  {item['q']}")
        results["answers"] = {"provider": out["provider"], "accuracy": round(sum(r["correct"] for r in rows) / len(rows), 3),
                              "seconds": round(time.perf_counter() - start, 1), "rows": rows}
        print(f"\nAnswer accuracy ({out['provider']}): {results['answers']['accuracy']:.0%}")

    (HERE / "results.json").write_text(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
