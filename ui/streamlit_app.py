"""Streamlit front end for the RAG API.

Run:  streamlit run ui/streamlit_app.py      (expects the API at $API_URL, default http://localhost:8000)
"""
import os

import requests
import streamlit as st

API = os.getenv("API_URL", "http://localhost:8000")
EXAMPLES = [
    "What is Entrata's target price and how was it derived?",
    "How were daily FX rates converted for the Budget INR measure?",
    "What share of defaulted balance does the expected-loss list reach at 20% capacity?",
    "Why did gradient boosting lose to logistic regression in the campaign model?",
]

st.set_page_config(page_title="Document Q&A", page_icon="📄", layout="wide")


def api(method: str, path: str, **kw):
    r = requests.request(method, f"{API}{path}", timeout=300, **kw)
    if r.status_code >= 400:
        detail = r.json().get("detail", r.text) if r.headers.get("content-type", "").startswith("application/json") else r.text
        raise RuntimeError(detail)
    return r.json() if r.content else None


with st.sidebar:
    st.header("Library")
    try:
        health = api("GET", "/health")
    except (requests.ConnectionError, RuntimeError) as e:
        st.error(f"API not reachable at {API}. Start it with `uvicorn app.api:app`.\n\n{e}")
        st.stop()
    st.caption(f"Answer model: **{health['llm']}** · {health['documents']} documents · {health['chunks']} chunks")

    uploads = st.file_uploader("Add PDF, TXT or MD files", type=["pdf", "txt", "md"], accept_multiple_files=True)
    if uploads and st.button("Add to library", type="primary"):
        with st.spinner("Reading, chunking and embedding..."):
            try:
                added = api("POST", "/documents", files=[("files", (u.name, u.getvalue())) for u in uploads])
                for d in added:
                    st.success(f"{d['filename']}: {d['chunks']} chunks" + (" (already in library)" if d["duplicate"] else ""))
            except RuntimeError as e:
                st.error(str(e))
        st.rerun()

    for doc in api("GET", "/documents"):
        c1, c2 = st.columns([5, 1])
        pages = f"{doc['pages']} pages · " if doc["pages"] else ""
        c1.markdown(f"**{doc['filename']}**  \n<small>{pages}{doc['chunks']} chunks</small>", unsafe_allow_html=True)
        if c2.button("✕", key=f"del-{doc['doc_id']}", help=f"Remove {doc['filename']}"):
            api("DELETE", f"/documents/{doc['doc_id']}")
            st.rerun()

    st.divider()
    mode = st.selectbox("Retrieval", ["hybrid", "vector", "bm25"],
                        help="Hybrid fuses vector similarity and BM25 keyword ranking with reciprocal rank fusion.")
    top_k = st.slider("Passages sent to the model", 2, 10, 5)

st.title("Ask your documents")
st.caption("Answers come only from the library on the left, with numbered citations back to the source page.")

if "chat" not in st.session_state:
    st.session_state.chat = []

cols = st.columns(2)
clicked = next((q for i, q in enumerate(EXAMPLES) if cols[i % 2].button(q, use_container_width=True)), None)


def render(turn: dict):
    with st.chat_message("user"):
        st.write(turn["question"])
    with st.chat_message("assistant"):
        st.write(turn["answer"])
        t = turn["timings_ms"]
        st.caption(f"{turn['provider']} · {turn['mode']} retrieval {t['retrieval']} ms · generation {t['generation']} ms")
        with st.expander(f"Sources ({sum(s['cited'] for s in turn['sources'])} cited of {len(turn['sources'])} retrieved)"):
            for s in turn["sources"]:
                ranks = ", ".join(f"{k} #{s[k + '_rank']}" for k in ("vector", "bm25") if s[k + "_rank"])
                st.markdown(f"**[{s['n']}] {s['label']}**{' · cited' if s['cited'] else ''}  \n"
                            f"<small>RRF {s['score']:.4f} · {ranks}</small>", unsafe_allow_html=True)
                st.text(s["text"][:700] + ("…" if len(s["text"]) > 700 else ""))


for turn in st.session_state.chat:
    render(turn)

question = st.chat_input("Ask a question about your documents") or clicked
if question:
    with st.spinner("Retrieving and answering..."):
        try:
            turn = api("POST", "/ask", json={"question": question, "top_k": top_k, "mode": mode})
        except RuntimeError as e:
            st.error(str(e))
            st.stop()
    st.session_state.chat.append(turn)
    render(turn)
