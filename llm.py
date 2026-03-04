"""Gemini LLM calls for transcript → notes generation."""

import os
import re
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview")

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


def _read_glossary(vault: Path) -> str:
    try:
        return (vault / "Glossary.md").read_text()
    except FileNotFoundError:
        return ""


def _build_notes_prompt(category: str | None, vault: Path) -> str:
    is_talk = category and category in _TALK_CATEGORIES
    base = _read_prompt("talk_notes") if is_talk else _read_prompt("meeting_notes")
    ref = _read_obsidian_ref()
    if ref:
        base += "\n\nOBSIDIAN FORMATTING REFERENCE:\n" + ref
    glossary = _read_glossary(vault)
    if glossary:
        base += "\n\nUSER'S KNOWN GLOSSARY (do NOT define these — only flag terms NOT in this list):\n" + glossary
    return base


@lru_cache(maxsize=1)
def _get_client():
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return None
    os.environ.pop("GOOGLE_GENAI_USE_VERTEXAI", None)
    from google import genai
    return genai.Client(api_key=api_key)


def _call_gemini(client, prompt: str, transcript: str,
                 temperature: float = 0.3) -> str | None:
    """Make a single Gemini call and return cleaned text, or None."""
    from google.genai import types

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt + "\n\nTRANSCRIPT:\n" + transcript,
        config=types.GenerateContentConfig(
            temperature=temperature,
            thinking_config=types.ThinkingConfig(thinking_level="high"),
        ),
    )
    if not response.text or not response.text.strip():
        return None
    return re.sub(r"\n{3,}", "\n\n", response.text.strip())

# ── Public API ───────────────────────────────────────────────────────────────

def generate_notes(transcript: str, category: str | None,
                   meeting_num: int, vault: Path | None = None) -> str | None:
    """Generate notes + action items from transcript text.

    Returns combined markdown string, or None on failure.
    """
    client = _get_client()
    if client is None:
        return None

    is_talk = category and category in _TALK_CATEGORIES

    # Build notes prompt
    vault = vault or Path(os.getenv("OBSIDIAN_VAULT",
                                    str(Path.home() / "Desktop" / "Obsidian Vault")))
    prompt = _build_notes_prompt(category, vault)
    prompt += f"\nThis is meeting #{meeting_num} in this series. Start the title as `# {meeting_num}: <title>`.\n"

    if is_talk:
        # Talks: single call, no action items
        notes = _call_gemini(client, prompt, transcript, temperature=0.3)
        return notes

    # Meetings: run notes + action items in parallel
    with ThreadPoolExecutor(max_workers=2) as pool:
        notes_future = pool.submit(_call_gemini, client, prompt, transcript, 0.3)
        actions_future = pool.submit(_call_gemini, client, _read_prompt("action_items"),
                                     transcript, 0.2)
        notes = notes_future.result()
        action_items = actions_future.result()

    if notes is None:
        return None

    if action_items:
        return notes + "\n\n" + action_items
    return notes
