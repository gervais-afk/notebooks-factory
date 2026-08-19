#!/usr/bin/env python3
"""
secrets_loader.py — Unified API Key & LLM Provider Manager
===========================================================
Priority chain for API keys (most secure first):
  1. st.secrets["KEY"]           — Streamlit Community Cloud / local secrets.toml
  2. os.environ["KEY"]           — Docker / .env file / system env
  3. fallback to ""              — Explicit missing key (never silently swallowed)

LLM Routing Strategy:
  PRIMARY  → Google Gemini (google-generativeai SDK)
  FALLBACK → OpenRouter  (OpenAI-compatible REST API, 200+ models)

Usage:
    from secrets_loader import get_gemini_key, get_openrouter_key, call_llm
    response = call_llm("What is overfitting?")
"""

import os
import json
import requests
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# § 1.  Key Resolution (Streamlit Cloud ↔ Local .env)
# ─────────────────────────────────────────────────────────────────────────────

def _resolve(key: str) -> str:
    """
    Resolve an API key with priority:
      1. st.secrets  (Streamlit Community Cloud or local .streamlit/secrets.toml)
      2. os.environ  (.env / Docker / system)
      3. empty string (callers must handle this case explicitly)
    """
    # Try Streamlit secrets first (available on Cloud and local with secrets.toml)
    try:
        import streamlit as st
        val = st.secrets.get(key, "")
        if val:
            return val
    except Exception:
        pass

    # Then fall back to environment variable
    return os.environ.get(key, "")


def get_gemini_key() -> str:
    """Return active Gemini API key or empty string."""
    return _resolve("GEMINI_API_KEY") or _resolve("GOOGLE_API_KEY")


def get_openrouter_key() -> str:
    """Return active OpenRouter API key or empty string."""
    return _resolve("OPENROUTER_API_KEY")


def get_openrouter_model() -> str:
    return _resolve("OPENROUTER_MODEL") or "google/gemma-2-27b-it"


def get_openrouter_site() -> tuple[str, str]:
    url  = _resolve("OPENROUTER_SITE_URL")  or "https://dataset-automator.streamlit.app"
    name = _resolve("OPENROUTER_SITE_NAME") or "Dataset Automator"
    return url, name


# ─────────────────────────────────────────────────────────────────────────────
# § 2.  Gemini Caller
# ─────────────────────────────────────────────────────────────────────────────

def _call_gemini(prompt: str, model_name: str = "gemini-2.5-flash") -> str:
    """
    Call Google Gemini via google-generativeai SDK.
    Tries requested model, then falls back to gemini-1.5-flash / gemini-2.5-flash-latest.
    Raises RuntimeError if key is missing or all Gemini models fail.
    """
    key = get_gemini_key()
    if not key:
        raise RuntimeError("GEMINI_API_KEY not configured.")

    import google.generativeai as genai
    genai.configure(api_key=key)

    candidate_models = [model_name, "gemini-2.5-flash", "gemini-1.5-flash", "gemini-1.5-pro"]
    seen = set()
    last_err = None

    for m_name in candidate_models:
        if m_name in seen:
            continue
        seen.add(m_name)
        try:
            model = genai.GenerativeModel(m_name)
            response = model.generate_content(prompt)
            if response and response.text:
                return response.text
        except Exception as e:
            last_err = e
            continue

    raise RuntimeError(f"All Gemini models failed. Last error: {last_err}")


# ─────────────────────────────────────────────────────────────────────────────
# § 3.  OpenRouter Caller (Fallback)
# ─────────────────────────────────────────────────────────────────────────────

def _call_openrouter(prompt: str, model: Optional[str] = None, system: str = "") -> str:
    """
    Call OpenRouter (OpenAI-compatible REST endpoint).
    Raises RuntimeError if key is missing or HTTP call fails.
    """
    key = get_openrouter_key()
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY not configured.")

    model = model or get_openrouter_model()
    site_url, site_name = get_openrouter_site()

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    resp = requests.post(
        url="https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {key}",
            "HTTP-Referer": site_url,
            "X-Title": site_name,
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": messages,
            "max_tokens": 1500,
            "temperature": 0.4,
        },
        timeout=45,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


# ─────────────────────────────────────────────────────────────────────────────
# § 4.  Unified call_llm() — Primary + Fallback
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = (
    "You are Antigravity Copilot, the expert MLOps assistant for Dataset Automator. "
    "You orchestrate Google TabFM models, the What-If analyzer, EU AI Act compliance, "
    "and adversarial red-team audits. Be concise, technical, and structured."
)


def call_llm(
    prompt: str,
    model_name: str = "gemini-2.0-flash",
    openrouter_model: Optional[str] = None,
    system: str = SYSTEM_PROMPT,
) -> dict:
    """
    Call LLM with automatic Gemini → OpenRouter fallback.

    Returns:
        {
            "text":     str,          # model output
            "provider": str,          # "gemini" | "openrouter" | "offline"
            "model":    str,          # model identifier used
            "error":    str | None,   # error chain if fallback triggered
        }
    """
    full_prompt = f"{system}\n\n{prompt}" if system else prompt

    # ── Attempt 1: Gemini ──────────────────────────────────────────────────
    try:
        text = _call_gemini(full_prompt, model_name=model_name)
        return {"text": text, "provider": "gemini", "model": model_name, "error": None}
    except Exception as e_gemini:
        gemini_error = str(e_gemini)

    # ── Attempt 2: OpenRouter ─────────────────────────────────────────────
    try:
        or_model = openrouter_model or get_openrouter_model()
        text = _call_openrouter(prompt, model=or_model, system=system)
        return {
            "text": text,
            "provider": "openrouter",
            "model": or_model,
            "error": f"Gemini unavailable ({gemini_error}), switched to OpenRouter.",
        }
    except Exception as e_or:
        openrouter_error = str(e_or)

    # ── Attempt 3: Offline graceful degradation ───────────────────────────
    return {
        "text": (
            "⚠️ **Both LLM providers are currently unreachable.**\n\n"
            f"- Gemini error: `{gemini_error}`\n"
            f"- OpenRouter error: `{openrouter_error}`\n\n"
            "The app's ML pipeline, audits, and notebook generation remain fully functional "
            "without an active LLM connection. Please check your API keys in "
            "**Settings → Secrets** on Streamlit Cloud, or in your local `.env` file."
        ),
        "provider": "offline",
        "model": "none",
        "error": f"Gemini: {gemini_error} | OpenRouter: {openrouter_error}",
    }


# ─────────────────────────────────────────────────────────────────────────────
# § 5.  Diagnostic — which keys are active?
# ─────────────────────────────────────────────────────────────────────────────

def get_api_status() -> dict:
    """
    Return a non-sensitive status dict for the sidebar/telemetry banner.
    Keys are masked (first 8 chars + '…').
    """
    gemini_key = get_gemini_key()
    or_key     = get_openrouter_key()

    def _mask(k: str) -> str:
        return k[:8] + "…" if k else "❌ Not configured"

    return {
        "gemini_configured": bool(gemini_key),
        "gemini_key_preview": _mask(gemini_key),
        "openrouter_configured": bool(or_key),
        "openrouter_key_preview": _mask(or_key),
        "openrouter_model": get_openrouter_model(),
        "active_provider": "gemini" if gemini_key else ("openrouter" if or_key else "offline"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# § 6.  Self-Test
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=== API Status Diagnostic ===")
    status = get_api_status()
    for k, v in status.items():
        print(f"  {k}: {v}")
    print("\n=== Live LLM Test ===")
    result = call_llm("In one sentence, what is Google TabFM?")
    print(f"  Provider : {result['provider']}")
    print(f"  Model    : {result['model']}")
    print(f"  Response : {result['text'][:200]}")
    if result["error"]:
        print(f"  Warning  : {result['error']}")
