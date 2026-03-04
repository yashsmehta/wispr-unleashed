"""Gemini LLM calls for transcript → notes generation."""

import os
import re
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview")

_OBSIDIAN_REF = Path(__file__).parent / "obsidian-reference.md"

_TALK_CATEGORIES = {"Talks", "Classes", "Lectures", "Seminars"}

# ── Prompts ──────────────────────────────────────────────────────────────────

MEETING_NOTES_PROMPT = """\
You are processing a raw transcript of a research meeting — typically a discussion about a research project with a professor or collaborators.

Rules:
- Start with `# N: Title` where N is the meeting number provided below. The title should be short, punchy, and descriptive of the key topics (e.g. "# 11: Pre-ReLU Analysis & Paper Strategy"). NOT a paper title, NOT the date, NOT generic labels. Keep the title under 8 words
- Extract the key ideas, questions, and technical details discussed
- Capture any suggested approaches, references, or directions that came up
- Do NOT include action items or to-do lists — those will be extracted separately
- Group by topic, not chronological order — let the structure emerge from the content
- Preserve specific paper names, method names, equations, URLs, and proper nouns exactly
- Use terse bullet points — no filler, no "we discussed", no meta-commentary
- Be concise — every word must carry information
- Use whatever heading structure best fits the content — don't force a rigid template
- Use Obsidian-flavored markdown: callouts (`> [!tip]`, `> [!question]`, etc.), ==highlights== for key results, $LaTeX$ for math, and tables where they aid clarity. See the formatting reference below for available features.
- Do NOT include any preamble, disclaimer, or labels — just the notes
- Keep whitespace minimal — no extra blank lines between sections. One blank line before headings, no blank lines between bullet points
- Preserve specific numbers, thresholds, and quantitative details mentioned (e.g., "6 or 64 categories", "up to Conv4", "epoch 1 to 20")
- At the end, add a `> [!study] New Terms` callout listing any technical terms, concepts, or techniques from the transcript that are NOT in the user's known glossary (provided below). Give each a brief 1-2 sentence definition. Skip this section if there are no new terms. Be conservative — do NOT flag terms that are obviously central to the project being discussed or that any researcher in the field would know.
"""

ACTION_ITEMS_PROMPT = """\
You are extracting action items from a raw transcript of a research project meeting.

Your job is to carefully identify every task, next step, or commitment that was discussed — whether explicitly stated or implicitly agreed upon.

Rules:
- For EACH action item, be specific and detailed: include the exact method, dataset, parameter, metric, or approach discussed. Do NOT summarize vaguely (e.g., "run more experiments"). Instead, spell out what the experiment is, what data to use, and what to measure.
- Do NOT attribute action items to specific people. Just list what needs to be done for the project.
- Include decisions that imply work (e.g., "let's use log scale" → regenerate the plot with log-scale x-axis)
- Include deprioritized items too, but mark them (e.g., "low priority" or "not blocking")
- Output format: a single Obsidian callout block using `> [!todo] Action Items` with checkboxes
- Each item: `- [ ] Detailed description of what to do`
- If no action items exist, output nothing
"""

TALK_NOTES_PROMPT = """\
You are processing a raw transcript of an academic presentation — either a research talk (~45 min, one speaker presenting their work) or a class lecture (~1 hour).

Rules:
- Start with a `# Title` — short, punchy, and descriptive of the key topics (e.g. "Attention Is All You Need" or "Convex Optimization Basics"). NOT the date, NOT generic labels like "Lecture Notes". Keep it under 8 words
- Capture the core argument: what problem, what approach, why it matters, what they found
- Extract key ideas, concepts, and distinctions the speaker introduces
- Note methods, results, and any specific numbers or comparisons
- Record referenced papers, people, and tools
- For classes: capture definitions, frameworks, and worked examples
- Note open problems, limitations, or future directions the speaker raises
- Preserve technical terms, equations, and proper nouns exactly
- Use terse bullet points — no filler, no "the speaker discussed"
- Be concise — every word must carry information
- Use whatever heading structure best fits the content — don't force a rigid template
- Use Obsidian-flavored markdown: callouts (`> [!tip]`, `> [!question]`, `> [!example]`, etc.), ==highlights== for key results, $LaTeX$ for math, and tables where they aid clarity. See the formatting reference below for available features.
- Do NOT include any preamble, disclaimer, or labels — just the notes
- Keep whitespace minimal — no extra blank lines between sections. One blank line before headings, no blank lines between bullet points
- At the end, add a `> [!study] New Terms` callout listing any technical terms, concepts, or techniques from the transcript that are NOT in the user's known glossary (provided below). Give each a brief 1-2 sentence definition. Skip this section if there are no new terms.
"""

# ── Helpers ──────────────────────────────────────────────────────────────────

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
    base = TALK_NOTES_PROMPT if is_talk else MEETING_NOTES_PROMPT
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
        actions_future = pool.submit(_call_gemini, client, ACTION_ITEMS_PROMPT,
                                     transcript, 0.2)
        notes = notes_future.result()
        action_items = actions_future.result()

    if notes is None:
        return None

    if action_items:
        return notes + "\n\n" + action_items
    return notes
