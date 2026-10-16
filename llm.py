"""LLM calls for transcript → notes generation.

Supports two headless CLI backends configured via LLM_PROVIDER in .env:
- `claude`: locally logged-in Claude Code CLI (`claude -p`), using subscription auth.
- `antigravity` (`agy`): Antigravity CLI with Gemini 4 Argon (`agy -p`), using
  machine Google Cloud ADC API billing (`AGY_ADC_AUTH=true`).
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent
load_dotenv(ROOT_DIR / ".env")

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "antigravity").lower()
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")
CLAUDE_EFFORT = os.getenv("CLAUDE_EFFORT", "medium")
AGY_MODEL = os.getenv("AGY_MODEL", "gemini-4-argon-high")
CLAUDE_TIMEOUT = 600  # seconds per call

_OBSIDIAN_REF = Path(__file__).parent / "obsidian-reference.md"
_PROMPTS_DIR = Path(__file__).parent / "prompts"


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


def _build_notes_prompt() -> str:
    base = _read_prompt("notes")
    ref = _read_obsidian_ref()
    if ref:
        base += "\n\nOBSIDIAN FORMATTING REFERENCE:\n" + ref
    return base


@lru_cache(maxsize=1)
def _read_context_sections() -> tuple[str, dict[str, str]]:
    """Parse prompts/context.md into (global_preamble, {folder_key: paragraph})."""
    try:
        raw = _read_prompt("context")
    except FileNotFoundError:
        return "", {}

    parts = re.split(r"(?m)^##\s+(.+?)\s*$", raw)
    global_ctx = parts[0].strip()
    sections: dict[str, str] = {}
    for i in range(1, len(parts), 2):
        key = parts[i].strip().strip("/").lower()
        body = parts[i + 1].strip()
        if key and body:
            sections[key] = body
    return global_ctx, sections


def _resolve_folder_context(folder: str = "") -> str:
    """Return global context plus any matching category/subfolder paragraphs."""
    global_ctx, sections = _read_context_sections()
    blocks: list[str] = []
    if global_ctx:
        blocks.append(global_ctx)

    norm = folder.strip().strip("/")
    if norm and norm != ".":
        segments = [seg for seg in norm.split("/") if seg]
        for depth in range(1, len(segments) + 1):
            prefix = "/".join(segments[:depth]).lower()
            if prefix in sections:
                blocks.append(sections[prefix])

    return "\n\n".join(blocks)


def _clean_note_markdown(text: str) -> str:
    """Sanitize LLM markdown so it renders cleanly in Obsidian and Vault Reader.

    - Strips standalone horizontal rule lines (`---`, `***`, `___`) from the body.
    - Normalizes section headings in the body so the top heading level is `###`
      (preventing `##` bottom-border lines from stacking with callouts/tables).
    - Collapses excess blank lines.
    """
    text = text.strip()
    if not text:
        return text

    parts = text.split("\n", 1)
    if len(parts) == 1:
        return parts[0]

    title, body = parts[0], parts[1]
    raw_lines = body.splitlines()

    # Check minimum heading level outside fenced code blocks
    in_fence = False
    min_h_level = 6
    for line in raw_lines:
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = re.match(r"^(#{1,6})\s+\S", line)
        if m:
            min_h_level = min(min_h_level, len(m.group(1)))

    shift = max(0, 3 - min_h_level) if min_h_level < 3 else 0

    cleaned_lines: list[str] = []
    in_fence = False
    for line in raw_lines:
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            cleaned_lines.append(line)
            continue
        if not in_fence:
            # Drop standalone horizontal rules (---, ***, ___)
            if re.match(r"^\s*([-*_])(\s*\1){2,}\s*$", line):
                continue
            if shift > 0:
                m = re.match(r"^(#{1,6})(\s+.*)$", line)
                if m:
                    new_level = min(6, len(m.group(1)) + shift)
                    line = "#" * new_level + m.group(2)
        cleaned_lines.append(line)

    joined = "\n".join([title, *cleaned_lines]).strip()
    return re.sub(r"\n{3,}", "\n\n", joined)


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


def _agy_command(system_prompt: str, transcript: str) -> list[str]:
    agy = shutil.which("agy") or str(Path.home() / ".local/bin/agy")
    combined_prompt = (
        f"{system_prompt}\n\n"
        "IMPORTANT: Do not call any tools or read/write any files. "
        "Respond directly with the note text only.\n\n"
        f"TRANSCRIPT:\n{transcript}"
    )
    return [
        agy,
        "--model", AGY_MODEL,
        "--output-format", "json",
        "--disable-slash-commands",
        f"-p={combined_prompt}",
    ]


def _call_agy(system_prompt: str, transcript: str) -> str | None:
    env = dict(os.environ)
    env["AGY_ADC_AUTH"] = os.getenv("AGY_ADC_AUTH", "true")
    with tempfile.TemporaryDirectory() as cwd:
        proc = subprocess.run(
            _agy_command(system_prompt, transcript),
            stdin=subprocess.DEVNULL,
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
        raise RuntimeError(f"agy exited {proc.returncode}: {detail}") from None
    if payload.get("is_error") or (
        payload.get("status") and payload.get("status") != "SUCCESS"
    ):
        raise RuntimeError(
            f"agy error: {payload.get('error') or payload.get('response') or payload}"
        )
    return payload.get("response") or payload.get("result")


def _call_claude(system_prompt: str, transcript: str) -> str | None:
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
    return payload.get("result")


def _call_llm(
    system_prompt: str, transcript: str, *, provider: str | None = None
) -> str | None:
    """Make a headless LLM call (Antigravity default, falling back to Claude Code)."""
    active_provider = (provider or LLM_PROVIDER).strip().lower()
    if active_provider in ("antigravity", "agy"):
        try:
            text = _call_agy(system_prompt, transcript)
        except Exception as agy_exc:
            if provider is not None:
                raise
            try:
                text = _call_claude(system_prompt, transcript)
            except Exception:
                raise agy_exc from None
    else:
        text = _call_claude(system_prompt, transcript)

    if not text or not text.strip():
        return None
    return _clean_note_markdown(text)


# ── Public API ───────────────────────────────────────────────────────────────


def generate_notes(
    transcript: str,
    meeting_num: int,
    *,
    user_name: str = "",
    folder: str = "",
    user_context: str = "",
    provider: str | None = None,
) -> str | None:
    """Generate notes from transcript text in a single call.

    The LLM decides the structure (meeting, lecture, brainstorm, …) from the
    content. Returns markdown whose first line is the title, or None on failure.
    """
    prompt = _build_notes_prompt()

    folder_ctx = _resolve_folder_context(folder)
    if folder_ctx:
        prompt += "\n\nCONTEXT:\n" + folder_ctx
    elif user_name:
        prompt += (
            f"\n\nThe user's name is {user_name}. Use this only when it helps "
            "disambiguate speakers; do not invent speaker identities."
        )

    if user_context and user_context.strip():
        prompt += f"\n\nAdditional context for this recording: {user_context.strip()}"

    prompt += f"\nThis is note #{meeting_num} in this folder.\n"
    return _call_llm(prompt, transcript, provider=provider)



