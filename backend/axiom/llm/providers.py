"""Free / local LLM providers, all spoken to through the OpenAI-compatible chat API.

Only `base_url`, key and model differ, so swapping or adding a provider is one entry here. A provider
without credentials is skipped, which lets the same code run on Groq, Gemini, OpenRouter free models,
or fully offline on Ollama.
"""

from __future__ import annotations

from dataclasses import dataclass

from axiom.config import ON_SERVERLESS, Settings, get_settings


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    base_url: str
    api_key: str
    model: str
    timeout: float = 90.0
    extra_body: dict | None = None


def _catalog(s: Settings) -> dict[str, ProviderSpec | None]:
    return {
        "groq": ProviderSpec("groq", "https://api.groq.com/openai/v1", s.groq_api_key, s.groq_model)
        if s.groq_api_key
        else None,
        "cerebras": ProviderSpec(
            "cerebras", "https://api.cerebras.ai/v1", s.cerebras_api_key, s.cerebras_model
        )
        if s.cerebras_api_key
        else None,
        "gemini": ProviderSpec(
            "gemini",
            "https://generativelanguage.googleapis.com/v1beta/openai/",
            s.gemini_api_key,
            s.gemini_model,
        )
        if s.gemini_api_key
        else None,
        "openrouter": ProviderSpec(
            "openrouter",
            "https://openrouter.ai/api/v1",
            s.openrouter_api_key,
            s.openrouter_model,
            # free OpenRouter models are mostly reasoning models that spend max_tokens thinking
            extra_body={"reasoning": {"effort": s.openrouter_reasoning_effort}}
            if s.openrouter_reasoning_effort
            else None,
        )
        if s.openrouter_api_key
        else None,
        # Ollama ignores the key but the SDK requires a non-empty string. Local models are slower.
        "ollama": ProviderSpec(
            "ollama",
            s.ollama_base_url,
            "ollama",
            s.ollama_model,
            timeout=300.0,
            extra_body={"reasoning_effort": s.ollama_reasoning_effort} if s.ollama_reasoning_effort else None,
        ),
    }


def build_chain(settings: Settings | None = None) -> list[ProviderSpec]:
    """Providers in configured fallback order, skipping any without credentials."""
    s = settings or get_settings()
    catalog = _catalog(s)
    chain = []
    for name in (n.strip() for n in s.llm_chain.split(",") if n.strip()):
        if name not in catalog:
            raise ValueError(f"Unknown LLM provider {name!r} in LLM_CHAIN; known: {sorted(catalog)}")
        if name == "ollama" and ON_SERVERLESS and "localhost" in s.ollama_base_url:
            continue  # nothing listens on localhost in a serverless function; it would only burn the 300s timeout
        if catalog[name] is not None:
            chain.append(catalog[name])
    return chain
