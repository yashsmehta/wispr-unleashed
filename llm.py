"""LLM calls for transcript → notes generation.

Runs the locally logged-in Claude Code CLI headless (`claude -p`), so no API
key is needed. Set CLAUDE_MODEL / CLAUDE_EFFORT in .env to override defaults.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent
load_dotenv(ROOT_DIR / ".env")

CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")
CLAUDE_EFFORT = os.getenv("CLAUDE_EFFORT", "medium")
CLAUDE_TIMEOUT = 600  # seconds per call

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


def _claude_command(system_prompt: str) -> list[str]:
    claude = shutil.which("claude") or str(Path.home() / ".local/bin/claude")
    return [
        claude,
        "-p",
        "--model", CLAUDE_MODEL,
        "--effort", CLAUDE_EFFORT,
        "--system-prompt", system_prompt,
        "--tools", "",
        "--strict-mcp-config",
        "--no-session-persistence",
        "--output-format", "json",
    ]


def _call_llm(system_prompt: str, transcript: str) -> str | None:
    """Make a single headless Claude Code call and return cleaned text, or None."""
    # Drop any API key so the CLI uses the logged-in Claude account, and run
    # from an empty dir so no project CLAUDE.md leaks into the prompt.
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    with tempfile.TemporaryDirectory() as cwd:
        proc = subprocess.run(
            _claude_command(system_prompt),
            input=transcript,
            capture_output=True,
            text=True,
            cwd=cwd,
            env=env,
            timeout=CLAUDE_TIMEOUT,
        )
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        detail = (proc.stderr or proc.stdout).strip()[-300:]
        raise RuntimeError(f"claude exited {proc.returncode}: {detail}") from None
    if payload.get("is_error"):
        raise RuntimeError(f"claude error: {payload.get('result')}")
    text = payload.get("result")
    if not text or not text.strip():
        return None
    return re.sub(r"\n{3,}", "\n\n", text.strip())


# ── Public API ───────────────────────────────────────────────────────────────


def generate_notes(
    transcript: str, category: str | None, meeting_num: int, *, user_name: str = ""
) -> str | None:
    """Generate notes + action items from transcript text.

    Returns combined markdown string, or None on failure.
    """
    is_talk = category and category in _TALK_CATEGORIES

    prompt = _build_notes_prompt(category)
    if user_name:
        prompt += (
            f"\n\nThe user's name is {user_name}. Use this only when it helps "
            "disambiguate speakers; do not invent speaker identities."
        )
    prompt += f"\nThis is meeting #{meeting_num} in this series.\n"

    if is_talk:
        return _call_llm(prompt, transcript)

    # Meetings: run notes + action items in parallel
    with ThreadPoolExecutor(max_workers=2) as pool:
        notes_future = pool.submit(_call_llm, prompt, transcript)
        actions_future = pool.submit(
            _call_llm, _read_prompt("action_items"), transcript
        )
        notes = notes_future.result()
        action_items = actions_future.result()

    if notes is None:
        return None

    if action_items:
        return notes + "\n\n" + action_items
    return notes
