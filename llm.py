"""LLM calls for transcript → notes generation.

Uses litellm to support any provider (OpenAI, Anthropic, Google, etc.).
Set LLM_MODEL and the corresponding API key in .env.
"""

import os
import re
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path

import litellm

litellm.suppress_debug_info = True

# Support legacy GOOGLE_GENAI_USE_VERTEXAI=True by mapping to vertex_ai/ prefix
_USE_VERTEX = os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").lower() == "true"
_DEFAULT_MODEL = "gemini/gemini-3.1-pro-preview"
LLM_MODEL = os.getenv("LLM_MODEL", _DEFAULT_MODEL)

# Map GOOGLE_CLOUD_PROJECT → VERTEXAI_PROJECT for litellm
if _USE_VERTEX and not os.getenv("VERTEXAI_PROJECT"):
    gcp_project = os.getenv("GOOGLE_CLOUD_PROJECT")
    if gcp_project:
        os.environ["VERTEXAI_PROJECT"] = gcp_project

_OBSIDIAN_REF = Path(__file__).parent / "obsidian-reference.md"
_PROMPTS_DIR = Path(__file__).parent / "prompts"

_TALK_CATEGORIES = {"Talks", "Classes", "Lectures", "Seminars"}

# ── Helpers ──────────────────────────────────────────────────────────────────

@lru_cache(maxsize=None)
def _read_prompt(name: str) -> str:
    return (_PROMPTS_DIR / f"{name}.md").read_text()


@lru_cache(maxsize=1)
def _read_obsidian_ref() -> str:
    try:
        return _OBSIDIAN_REF.read_text()
    except FileNotFoundError:
        return ""


def _build_notes_prompt(category: str | None) -> str:
    is_talk = category and category in _TALK_CATEGORIES
    base = _read_prompt("talk_notes") if is_talk else _read_prompt("meeting_notes")
    ref = _read_obsidian_ref()
    if ref:
        base += "\n\nOBSIDIAN FORMATTING REFERENCE:\n" + ref
    return base


def _call_llm(system_prompt: str, transcript: str,
              temperature: float = 0.3) -> str | None:
    """Make a single LLM call and return cleaned text, or None."""
    response = litellm.completion(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": transcript},
        ],
        temperature=temperature,
        max_tokens=16384,
        thinking={"type": "enabled", "budget_tokens": 20000},
        allowed_openai_params=["thinking"],
    )
    text = response.choices[0].message.content
    if not text or not text.strip():
        return None
    return re.sub(r"\n{3,}", "\n\n", text.strip())

# ── Public API ───────────────────────────────────────────────────────────────

def generate_notes(transcript: str, category: str | None,
                   meeting_num: int, **_kwargs) -> str | None:
    """Generate notes + action items from transcript text.

    Returns combined markdown string, or None on failure.
    """
    is_talk = category and category in _TALK_CATEGORIES

    prompt = _build_notes_prompt(category)
    prompt += f"\nThis is meeting #{meeting_num} in this series.\n"

    if is_talk:
        return _call_llm(prompt, transcript, temperature=0.3)

    # Meetings: run notes + action items in parallel
    with ThreadPoolExecutor(max_workers=2) as pool:
        notes_future = pool.submit(_call_llm, prompt, transcript, 0.3)
        actions_future = pool.submit(_call_llm, _read_prompt("action_items"),
                                     transcript, 0.2)
        notes = notes_future.result()
        action_items = actions_future.result()

    if notes is None:
        return None

    if action_items:
        return notes + "\n\n" + action_items
    return notes
