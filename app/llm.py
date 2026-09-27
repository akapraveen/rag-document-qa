"""Answer generators: Claude (Anthropic SDK), a local Ollama model, or no LLM at all (extractive)."""
import os

import requests

from app.config import Settings


class GenerationError(RuntimeError):
    pass


class ClaudeGenerator:
    def __init__(self, model: str):
        import anthropic
        self.client = anthropic.Anthropic()
        self.model = model
        self.name = f"claude ({model})"

    def generate(self, system: str, prompt: str) -> str:
        import anthropic
        request = dict(model=self.model, max_tokens=16000, system=system,
                       messages=[{"role": "user", "content": prompt}])
        try:
            if self.model == "claude-opus-5":
                # Server-side fallback re-runs a policy-declined request on Anthropic's recommended model.
                response = self.client.beta.messages.create(
                    **request, betas=["server-side-fallback-2026-07-01"], fallbacks="default")
            else:
                response = self.client.messages.create(**request)
        except anthropic.RateLimitError as e:
            raise GenerationError("Claude rate limit reached; try again shortly") from e
        except anthropic.APIStatusError as e:
            raise GenerationError(f"Claude API error {e.status_code}: {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise GenerationError("Could not reach the Claude API") from e
        if response.stop_reason == "refusal":
            raise GenerationError("Claude declined to answer this request")
        return "".join(b.text for b in response.content if b.type == "text").strip()


class OllamaGenerator:
    def __init__(self, model: str, host: str):
        import ollama
        self.client = ollama.Client(host=host)
        self.model = model
        self.name = f"ollama ({model})"

    def generate(self, system: str, prompt: str) -> str:
        try:
            response = self.client.chat(model=self.model, options={"temperature": 0.1},
                                        messages=[{"role": "system", "content": system},
                                                  {"role": "user", "content": prompt}])
        except Exception as e:  # the ollama client raises several unrelated types (HTTP, connection, model)
            raise GenerationError(f"Ollama error: {e}") from e
        return response.message.content.strip()


def _ollama_has(model: str, host: str) -> bool:
    try:
        tags = requests.get(f"{host}/api/tags", timeout=2).json().get("models", [])
    except requests.RequestException:
        return False
    names = {m["name"] for m in tags} | {m["name"].split(":")[0] for m in tags}
    return model in names


def pick_generator(settings: Settings):
    """Returns a generator, or None for extractive mode (quotes the best passages, no LLM)."""
    provider = settings.llm_provider
    has_claude_key = bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN"))
    if provider == "anthropic" or (provider == "auto" and has_claude_key):
        return ClaudeGenerator(settings.anthropic_model)
    if provider == "ollama" or (provider == "auto" and _ollama_has(settings.ollama_model, settings.ollama_host)):
        return OllamaGenerator(settings.ollama_model, settings.ollama_host)
    return None
