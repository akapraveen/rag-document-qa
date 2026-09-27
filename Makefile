.PHONY: install api ui test eval eval-answers web-corpus
install:
	python -m venv .venv && .venv/bin/pip install -r requirements.txt
api:
	.venv/bin/uvicorn app.api:app --reload --port 8000
ui:
	.venv/bin/streamlit run ui/streamlit_app.py
test:
	.venv/bin/python -m pytest -q
eval:
	.venv/bin/python -m eval.evaluate
eval-answers:
	.venv/bin/python -m eval.evaluate --answers
web-corpus:
	.venv/bin/python scripts/export_web_corpus.py
