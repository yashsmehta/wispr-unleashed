#!/usr/bin/env python3
"""Continuous meeting transcription using Wispr Flow.

Cycles Wispr Flow's hands-free recording (6-min limit per chunk),
polls its SQLite database for transcriptions, and assembles a
complete transcript into a single markdown file.

Usage: python3 record.py "Meeting Title"
"""

import atexit
import os
import re
import select
import signal
import sqlite3
import subprocess
import sys
import termios
import time
import tty
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ── Constants ────────────────────────────────────────────────────────────────

WISPR_DB = Path.home() / "Library" / "Application Support" / "Wispr Flow" / "flow.sqlite"
OBSIDIAN_VAULT = Path(os.getenv("OBSIDIAN_VAULT", str(Path.home() / "Documents" / "Obsidian Vault")))
TRANSCRIPTS_DIR = Path(os.getenv("TRANSCRIPTS_DIR", str(OBSIDIAN_VAULT / "Transcripts")))
PID_FILE = Path("/tmp/wispr-clawd.pid")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")
_OBSIDIAN_REF = Path(__file__).parent / "obsidian-reference.md"
POLL_INTERVAL = 5        # seconds between DB polls while recording
POLL_FAST = 1            # seconds between DB polls while waiting for transcription
RECORD_DURATION = 280    # 4m40s — stop before Wispr's "1 min left" warning at 5:00
PROCESS_TIMEOUT = 30     # seconds to wait for transcription after stopping
MAX_DURATION = 2 * 60 * 60  # 2 hour hard limit
DRAIN_TIMEOUT = 15       # seconds to wait for in-flight chunk after Ctrl+C

MEETING_NOTES_PROMPT = """\
You are processing a raw transcript of a research meeting — typically a discussion about a research project with a professor or collaborators.

Rules:
- Start with a `# Title` — short and descriptive of the actual content (e.g. "Sparse MoE Training Strategy"), NOT the date or generic labels like "Meeting Notes"
- Extract the key ideas, questions, and technical details discussed
- Capture any suggested approaches, references, or directions that came up
- If someone agreed to do something, note it as an action item with their name
- Group by topic, not chronological order — let the structure emerge from the content
- Preserve specific paper names, method names, equations, URLs, and proper nouns exactly
- Use terse bullet points — no filler, no "we discussed", no meta-commentary
- Be concise — every word must carry information
- Use whatever heading structure best fits the content — don't force a rigid template
- Use Obsidian-flavored markdown: callouts (`> [!tip]`, `> [!question]`, `> [!todo]`, etc.), ==highlights== for key results, $LaTeX$ for math, and tables where they aid clarity. See the formatting reference below for available features.
- Do NOT include any preamble, disclaimer, or labels — just the notes
"""

TALK_NOTES_PROMPT = """\
You are processing a raw transcript of an academic presentation — either a research talk (~45 min, one speaker presenting their work) or a class lecture (~1 hour).

Rules:
- Start with a `# Title` — short and descriptive of the actual content (e.g. "Attention Is All You Need" or "Convex Optimization Basics"), NOT the date or generic labels like "Lecture Notes"
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
"""

_TALK_CATEGORIES = {"Talks", "Classes", "Lectures", "Seminars"}


def _get_notes_prompt(category: str | None) -> str:
    base = TALK_NOTES_PROMPT if category and category in _TALK_CATEGORIES else MEETING_NOTES_PROMPT
    try:
        base += "\n\nOBSIDIAN FORMATTING REFERENCE:\n" + _OBSIDIAN_REF.read_text()
    except FileNotFoundError:
        pass
    return base

# ── Terminal formatting ──────────────────────────────────────────────────────

DIM = "\033[2m"
BOLD = "\033[1m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
RESET = "\033[0m"
HIDE_CURSOR = "\033[?25l"
SHOW_CURSOR = "\033[?25h"

DOT_EMPTY = f"{DIM}·{RESET}"
DOT_ACTIVE = f"{YELLOW}●{RESET}"
DOT_DONE = f"{GREEN}●{RESET}"
DOT_COUNT = 10


def put(msg: str):
    """Print a line, clearing any Wispr-pasted text first."""
    sys.stdout.write(f"\033[2K\r  {msg}\n")
    sys.stdout.flush()


def draw_dots(completed: int, active: bool, suffix: str = ""):
    """Draw the dot matrix with optional right-side annotation."""
    total = max(DOT_COUNT, completed + 1)
    dots = []
    for i in range(total):
        if i < completed:
            dots.append(DOT_DONE)
        elif i == completed and active:
            dots.append(DOT_ACTIVE)
        else:
            dots.append(DOT_EMPTY)
    line = " ".join(dots)
    if suffix:
        line += f"  {DIM}{suffix}{RESET}"
    sys.stdout.write(f"\033[2K\r  {line}")
    sys.stdout.flush()


# ── Interactive menu ─────────────────────────────────────────────────────────

class SelectMenu:
    """Arrow-key navigable menu. Assumes terminal is already in cbreak mode."""

    def __init__(self, items: list[str], prompt: str = ""):
        self.items = items
        self.prompt = prompt
        self.cursor = 0
        self._line_count = 0

    def _render(self):
        lines = []
        if self.prompt:
            lines.append(f"  {DIM}{self.prompt}{RESET}")
        for i, item in enumerate(self.items):
            if i == self.cursor:
                lines.append(f"  {CYAN}›{RESET} {BOLD}{item}{RESET}")
            else:
                lines.append(f"    {DIM}{item}{RESET}")
        lines.append(f"  {DIM}↑↓ enter esc{RESET}")

        sys.stdout.write("".join(f"\033[2K{line}\n" for line in lines))
        sys.stdout.flush()
        self._line_count = len(lines)

    def _erase(self):
        if self._line_count > 0:
            n = self._line_count
            sys.stdout.write(
                f"\033[{n}A" + "\033[2K\n" * n + f"\033[{n}A"
            )
            sys.stdout.flush()
            self._line_count = 0

    def _read_key(self) -> str:
        ch = sys.stdin.read(1)
        if ch == "\x1b":
            if select.select([sys.stdin], [], [], 0.05)[0]:
                ch2 = sys.stdin.read(1)
                if ch2 == "[":
                    ch3 = sys.stdin.read(1)
                    return {"A": "up", "B": "down"}.get(ch3, "")
            return "esc"
        if ch in ("\r", "\n"):
            return "enter"
        return ""

    def run(self) -> str | None:
        """Display menu, process arrow keys. Returns selected item or None."""
        flush_stdin()
        sys.stdout.write(HIDE_CURSOR)
        sys.stdout.write("\n")
        self._render()
        try:
            while True:
                key = self._read_key()
                if not key:
                    continue
                self._erase()
                if key == "up":
                    self.cursor = (self.cursor - 1) % len(self.items)
                elif key == "down":
                    self.cursor = (self.cursor + 1) % len(self.items)
                elif key == "enter":
                    return self.items[self.cursor]
                elif key == "esc":
                    return None
                self._render()
        finally:
            self._erase()
            sys.stdout.write(SHOW_CURSOR)
            sys.stdout.flush()


class FolderPicker:
    """Two-stage folder selection: category → subfolder."""

    def __init__(self):
        self.category: str | None = None
        self.subfolder: str | None = None
        self.completed = False

    def run(self, raw_mode: bool = False) -> bool:
        """Run the interactive picker. raw_mode=True if terminal is already cbreak."""
        categories = discover_categories()
        if not categories:
            return False

        fd = sys.stdin.fileno()
        old = None
        if not raw_mode:
            old = termios.tcgetattr(fd)
            tty.setcbreak(fd)
        try:
            menu = SelectMenu(categories, prompt="notes")
            choice = menu.run()
            if choice is None:
                return False
            self.category = choice

            subs = discover_subfolders(self.category)
            if subs:
                items = subs + ["(root)"]
                menu = SelectMenu(items, prompt=self.category)
                choice = menu.run()
                if choice is not None and choice != "(root)":
                    self.subfolder = choice

            self.completed = True
            return True
        finally:
            if old is not None:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)

    def label(self) -> str:
        if self.completed:
            parts = [self.category]
            if self.subfolder:
                parts.append(self.subfolder)
            return " › ".join(parts)
        return "any key → pick folder"

    def get_destination(self, heading: str) -> Path | None:
        if not self.completed or not self.category:
            return None
        dest = OBSIDIAN_VAULT / self.category
        if self.subfolder:
            dest = dest / self.subfolder
        date_str = datetime.now().strftime("%Y-%m-%d")
        slug = slugify(heading)
        notes_path = dest / f"{date_str}-{slug}.md"
        dest.mkdir(parents=True, exist_ok=True)
        return notes_path


# ── Helpers ──────────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return re.sub(r"-+", "-", text).strip("-")


def create_transcript_file(heading: str) -> Path:
    TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    slug = slugify(heading)
    base = TRANSCRIPTS_DIR / f"{date_str}-{slug}.md"

    path = base
    counter = 2
    while path.exists():
        path = TRANSCRIPTS_DIR / f"{date_str}-{slug}-{counter}.md"
        counter += 1

    now = datetime.now()
    path.write_text(
        f"# {heading}\n"
        f"*{now.strftime('%A, %B %-d, %Y')} · {now.strftime('%-I:%M %p')}*\n\n"
        f"---\n\n"
    )
    return path


def focus_terminal():
    """Bring terminal to foreground so Wispr's paste lands here harmlessly."""
    term = os.environ.get("TERM_PROGRAM", "")
    app_map = {
        "Apple_Terminal": "Terminal",
        "iTerm.app": "iTerm2",
        "ghostty": "Ghostty",
        "WezTerm": "WezTerm",
    }
    app_name = app_map.get(term, "Terminal")
    subprocess.run(["osascript", "-e", f'tell application "{app_name}" to activate'],
                   check=False, capture_output=True)


def flush_stdin():
    """Discard any text Wispr pasted into the terminal's input buffer."""
    try:
        termios.tcflush(sys.stdin.fileno(), termios.TCIFLUSH)
    except (termios.error, OSError):
        pass


def start_recording():
    subprocess.run(["open", "wispr-flow://start-hands-free"], check=False)


def stop_recording():
    focus_terminal()
    subprocess.run(["open", "wispr-flow://stop-hands-free"], check=False)


def get_utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f +00:00")


def poll_for_transcription(since_utc: str, known_ids: set) -> dict | None:
    try:
        conn = sqlite3.connect(f"file:{WISPR_DB}?mode=ro", uri=True)
    except sqlite3.OperationalError:
        return None
    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT transcriptEntityId, formattedText, numWords, duration
            FROM History
            WHERE timestamp >= ?
              AND status IN ('formatted', 'raw_transcript')
              AND formattedText IS NOT NULL
              AND formattedText != ''
            ORDER BY timestamp ASC
            """,
            (since_utc,),
        )
        row = cursor.fetchone()
        while row is not None:
            eid = row["transcriptEntityId"]
            if eid not in known_ids:
                return {
                    "id": eid,
                    "text": row["formattedText"],
                    "numWords": row["numWords"] or 0,
                    "duration": row["duration"] or 0.0,
                }
            row = cursor.fetchone()
    except sqlite3.OperationalError:
        pass
    finally:
        conn.close()
    return None


def discover_categories():
    """Find note category folders in Obsidian vault (excluding Transcripts)."""
    skip = {"transcripts", ".obsidian", ".trash"}
    categories = []
    for p in sorted(OBSIDIAN_VAULT.iterdir()):
        if p.is_dir() and p.name.lower() not in skip and not p.name.startswith("."):
            categories.append(p.name)
    return categories


def discover_subfolders(category: str):
    """Find subfolders within a category."""
    cat_dir = OBSIDIAN_VAULT / category
    subs = []
    for p in sorted(cat_dir.iterdir()):
        if p.is_dir() and not p.name.startswith("."):
            subs.append(p.name)
    return subs


def append_chunk(md_path: Path, chunk: dict):
    time_label = datetime.now().strftime("%-I:%M %p")
    with open(md_path, "a") as f:
        f.write(f"### {time_label}\n")
        f.write(chunk["text"].strip() + "\n\n")


def accept_chunk(result: dict, md_path: Path, known_ids: set, stats: dict):
    known_ids.add(result["id"])
    append_chunk(md_path, result)
    stats["chunks"] += 1
    stats["words"] += result["numWords"]
    stats["recording_time"] += result["duration"]


def write_footer(md_path: Path, stats: dict):
    end_time = datetime.now().strftime("%-I:%M %p")
    rec_minutes = int(stats["recording_time"] // 60)
    rec_seconds = int(stats["recording_time"] % 60)
    with open(md_path, "a") as f:
        f.write("---\n")
        f.write(f"*Ended {end_time} · {rec_minutes}m{rec_seconds:02d}s · {stats['words']:,} words*\n")


def _get_gemini_client():
    """Return a Gemini client using GOOGLE_API_KEY from env, or None."""
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return None
    os.environ.pop("GOOGLE_GENAI_USE_VERTEXAI", None)
    from google import genai
    return genai.Client(api_key=api_key)


def generate_notes(transcript_path: Path, notes_path: Path, heading: str,
                   category: str | None = None):
    """Generate notes from transcript using Gemini and save as a separate file."""
    transcript = transcript_path.read_text()
    if not transcript.strip():
        put(f"{DIM}skipped notes — empty transcript{RESET}")
        return

    client = _get_gemini_client()
    if client is None:
        put(f"{DIM}skipped notes — no API key{RESET}")
        return

    from google.genai import types

    prompt = _get_notes_prompt(category)

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt + "\n\nTRANSCRIPT:\n" + transcript,
            config=types.GenerateContentConfig(temperature=0.3),
        )
    except Exception as exc:
        put(f"{DIM}notes failed — {type(exc).__name__}{RESET}")
        return

    if not response.text or not response.text.strip():
        put(f"{DIM}notes failed — empty response{RESET}")
        return

    notes = re.sub(r"\n{3,}", "\n\n", response.text.strip())
    notes_path.write_text(notes + "\n")
    rel = notes_path.relative_to(OBSIDIAN_VAULT)
    put(f"{GREEN}✓{RESET} {DIM}{rel}{RESET}")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Usage: wispr <meeting title>")
        sys.exit(1)

    heading = sys.argv[1]

    if not WISPR_DB.exists():
        print("Wispr Flow not found. Is it installed?")
        sys.exit(1)

    interactive = sys.stdin.isatty()

    PID_FILE.write_text(str(os.getpid()))
    atexit.register(lambda: PID_FILE.unlink(missing_ok=True))

    shutdown_requested = False
    force_exit = False
    chunk_in_flight = False
    md_path = create_transcript_file(heading)
    known_ids: set = set()
    stats = {"chunks": 0, "words": 0, "recording_time": 0.0, "wall_time": 0.0}
    session_start = time.monotonic()
    folder_picker = FolderPicker()

    def handle_sigint(signum, frame):
        nonlocal shutdown_requested, force_exit
        if shutdown_requested:
            force_exit = True
            sys.exit(1)
        shutdown_requested = True

    signal.signal(signal.SIGINT, handle_sigint)

    print(f"\n  {BOLD}wispr{RESET} {DIM}·{RESET} {heading}\n")

    fd = sys.stdin.fileno() if interactive else -1
    old_term = termios.tcgetattr(fd) if interactive else None

    def redraw(active):
        draw_dots(stats["chunks"], active=active,
                  suffix=folder_picker.label() if interactive else "")

    try:
        if interactive:
            tty.setcbreak(fd)

        redraw(active=False)
        since_utc = get_utc_now()

        while not shutdown_requested:
            if time.monotonic() - session_start >= MAX_DURATION:
                sys.stdout.write("\n")
                put(f"{YELLOW}2h limit{RESET}")
                break

            since_utc = get_utc_now()
            redraw(active=True)
            start_recording()
            chunk_in_flight = True

            rec_start = time.monotonic()
            recording_active = True

            while not shutdown_requested:
                interval = POLL_FAST if not recording_active else POLL_INTERVAL

                if interactive:
                    readable, _, _ = select.select([sys.stdin], [], [], interval)
                    if readable:
                        if not folder_picker.completed:
                            try:
                                folder_picker.run(raw_mode=True)
                            except (KeyboardInterrupt, EOFError):
                                pass
                            redraw(active=recording_active)
                        else:
                            flush_stdin()
                else:
                    time.sleep(interval)

                result = poll_for_transcription(since_utc, known_ids)
                if result:
                    chunk_in_flight = False
                    accept_chunk(result, md_path, known_ids, stats)
                    flush_stdin()
                    redraw(active=False)
                    if recording_active:
                        shutdown_requested = True
                    break

                rec_elapsed = time.monotonic() - rec_start

                if recording_active and rec_elapsed >= RECORD_DURATION:
                    stop_recording()
                    recording_active = False

                if not recording_active and rec_elapsed >= RECORD_DURATION + PROCESS_TIMEOUT:
                    break

        stop_recording()

        if chunk_in_flight and not force_exit:
            drain_start = time.monotonic()
            while time.monotonic() - drain_start < DRAIN_TIMEOUT:
                if force_exit:
                    break
                result = poll_for_transcription(since_utc, known_ids)
                if result:
                    accept_chunk(result, md_path, known_ids, stats)
                    flush_stdin()
                    redraw(active=False)
                    break
                if interactive:
                    readable, _, _ = select.select([sys.stdin], [], [], POLL_FAST)
                    if readable:
                        flush_stdin()
                else:
                    time.sleep(POLL_FAST)

    finally:
        if old_term is not None:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_term)
        sys.stdout.write(SHOW_CURSOR)
        sys.stdout.write("\n\n")
        stats["wall_time"] = time.monotonic() - session_start
        write_footer(md_path, stats)

        if stats["chunks"] > 0 and interactive:
            if not folder_picker.completed:
                try:
                    folder_picker.run(raw_mode=False)
                except (KeyboardInterrupt, EOFError):
                    pass

            notes_path = folder_picker.get_destination(heading)
            if notes_path:
                put(f"{DIM}generating notes...{RESET}")
                generate_notes(md_path, notes_path, heading,
                               category=folder_picker.category)

        put(f"{DIM}{md_path.name}{RESET}")


if __name__ == "__main__":
    main()
