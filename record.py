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

from ui import (
    put, draw_dots, flush_stdin, FolderPicker, SelectMenu,
    DIM, BOLD, GREEN, YELLOW, CYAN, RESET, HIDE_CURSOR, SHOW_CURSOR,
)

load_dotenv()

# ── Constants ────────────────────────────────────────────────────────────────

WISPR_DB = Path.home() / "Library" / "Application Support" / "Wispr Flow" / "flow.sqlite"
OBSIDIAN_VAULT = Path(os.getenv("OBSIDIAN_VAULT", str(Path.home() / "Desktop" / "Obsidian Vault"))).expanduser()
TRANSCRIPTS_DIR = Path(os.getenv("TRANSCRIPTS_DIR", str(OBSIDIAN_VAULT / "Transcripts")))
PID_FILE = Path("/tmp/wispr-unleashed.pid")
USER_NAME = os.getenv("USER_NAME", "")
POLL_INTERVAL = 5        # seconds between DB polls while recording
POLL_FAST = 1            # seconds between DB polls while waiting for transcription
RECORD_DURATION = 295    # 4m55s — stop just before Wispr's 5-min warning
PROCESS_TIMEOUT = 30     # seconds to wait for transcription after stopping
MAX_DURATION = 2 * 60 * 60  # 2 hour hard limit
DRAIN_TIMEOUT = 15       # seconds to wait for in-flight chunk after Ctrl+C

# ── Helpers ──────────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text[:80].rstrip("-")


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


WINDOW_TITLE = "wispr-recording"


def set_window_title(title: str = WINDOW_TITLE):
    """Set the terminal window/tab title via ANSI escape."""
    sys.stdout.write(f"\033]0;{title}\007")
    sys.stdout.flush()


def focus_terminal():
    """Bring the recording terminal window to foreground so Wispr's paste lands here."""
    term = os.environ.get("TERM_PROGRAM", "")
    app_map = {
        "Apple_Terminal": "Terminal",
        "iTerm.app": "iTerm2",
        "ghostty": "Ghostty",
        "WezTerm": "WezTerm",
    }
    app_name = app_map.get(term, "Terminal")
    # Focus the specific window by title, not just the app
    script = f'''
        tell application "{app_name}"
            activate
            try
                set index of (first window whose name contains "{WINDOW_TITLE}") to 1
            end try
        end tell
    '''
    subprocess.run(["osascript", "-e", script], check=False, capture_output=True)


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


def _next_meeting_number(folder: Path) -> int:
    """Count existing .md files in folder to determine the next meeting number."""
    if not folder.exists():
        return 1
    return sum(1 for f in folder.iterdir() if f.suffix == ".md") + 1


def generate_notes(transcript_path: Path, dest_dir: Path, heading: str,
                   category: str | None = None):
    """Generate notes from transcript and save to dest_dir."""
    import llm

    transcript = transcript_path.read_text()
    if not transcript.strip():
        put(f"{DIM}skipped notes — empty transcript{RESET}")
        return

    meeting_num = _next_meeting_number(dest_dir)
    put(f"{DIM}generating notes…{RESET}")

    try:
        result = llm.generate_notes(transcript, category, meeting_num, vault=OBSIDIAN_VAULT)
    except Exception as exc:
        put(f"{YELLOW}⚠{RESET}  {DIM}notes failed — {exc}{RESET}")
        put(f"   {DIM}transcript saved, configure LLM_MODEL in .env to generate notes{RESET}")
        return

    if result is None:
        put(f"{YELLOW}⚠{RESET}  {DIM}notes failed — empty response{RESET}")
        return

    # Extract title from generated heading to build filename
    first_line = result.split("\n")[0]
    title_match = re.match(r"^#\s*(\d+):\s*(.+)$", first_line)
    if title_match:
        num = int(title_match.group(1))
        title = title_match.group(2).strip()
        filename = f"{num:02d} {title}.md"
    else:
        filename = f"{meeting_num:02d} {heading}.md"

    # Add YAML frontmatter with date
    date_str = datetime.now().strftime("%Y-%m-%d")
    content = f"---\ndate: {date_str}\n---\n\n{result}\n"

    notes_path = dest_dir / filename
    notes_path.write_text(content)
    rel = notes_path.relative_to(OBSIDIAN_VAULT)
    put(f"{GREEN}✓{RESET} {DIM}{rel}{RESET}")


# ── Main ─────────────────────────────────────────────────────────────────────

def prompt_title() -> str | None:
    """Prompt for a meeting title after recording. Returns None to keep default."""
    try:
        sys.stdout.write(f"  {DIM}meeting title (enter to keep default):{RESET} ")
        sys.stdout.flush()
        title = input().strip()
        return title if title else None
    except (KeyboardInterrupt, EOFError):
        return None


def rename_transcript(md_path: Path, new_heading: str) -> Path:
    """Rename transcript file and update the heading inside it."""
    date_str = datetime.now().strftime("%Y-%m-%d")
    slug = slugify(new_heading)
    new_path = md_path.parent / f"{date_str}-{slug}.md"
    if new_path == md_path:
        return md_path

    counter = 2
    base_path = new_path
    while new_path.exists():
        new_path = md_path.parent / f"{date_str}-{slug}-{counter}.md"
        counter += 1

    # Update heading inside the file
    content = md_path.read_text()
    old_heading_line = content.split("\n")[0]
    content = content.replace(old_heading_line, f"# {new_heading}", 1)
    md_path.write_text(content)
    md_path.rename(new_path)
    return new_path


def main():
    heading = sys.argv[1] if len(sys.argv) >= 2 else datetime.now().strftime("Recording %I:%M %p")

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
    folder_picker = FolderPicker(OBSIDIAN_VAULT)

    def handle_sigint(signum, frame):
        nonlocal shutdown_requested, force_exit
        if shutdown_requested:
            force_exit = True
            sys.exit(1)
        shutdown_requested = True

    signal.signal(signal.SIGINT, handle_sigint)

    set_window_title()
    print(f"\n  {BOLD}wispr{RESET} {DIM}·{RESET} {heading}\n")

    fd = sys.stdin.fileno() if interactive else -1
    old_term = termios.tcgetattr(fd) if interactive else None

    def redraw(active):
        draw_dots(stats["chunks"], active=active)

    try:
        if interactive:
            tty.setcbreak(fd)

        redraw(active=False)
        since_utc = get_utc_now()
        needs_stop = False

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
            needs_stop = True

            while not shutdown_requested:
                interval = POLL_FAST if not recording_active else POLL_INTERVAL

                if interactive:
                    readable, _, _ = select.select([sys.stdin], [], [], interval)
                    if readable:
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
                    needs_stop = False

                if not recording_active and rec_elapsed >= RECORD_DURATION + PROCESS_TIMEOUT:
                    sys.stdout.write("\n")
                    put(f"{YELLOW}⚠{RESET}  {DIM}transcript not received{RESET}")
                    put(f"   {DIM}open Wispr Flow to retry — waiting for transcript…{RESET}")
                    put(f"   {DIM}any key to skip this chunk and keep recording{RESET}")

                    # Keep polling — transcript may arrive after manual retry
                    while not shutdown_requested:
                        if interactive:
                            readable, _, _ = select.select([sys.stdin], [], [], POLL_FAST)
                            if readable:
                                flush_stdin()
                                # Check DB before assuming skip
                                result = poll_for_transcription(since_utc, known_ids)
                                if result:
                                    accept_chunk(result, md_path, known_ids, stats)
                                    put(f"{GREEN}✓{RESET}  {DIM}transcript recovered{RESET}")
                                    redraw(active=False)
                                else:
                                    put(f"   {DIM}skipped{RESET}")
                                chunk_in_flight = False
                                break
                        else:
                            time.sleep(POLL_FAST)

                        result = poll_for_transcription(since_utc, known_ids)
                        if result:
                            accept_chunk(result, md_path, known_ids, stats)
                            flush_stdin()
                            put(f"{GREEN}✓{RESET}  {DIM}transcript recovered{RESET}")
                            redraw(active=False)
                            chunk_in_flight = False
                            break
                    break

        if needs_stop:
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
        set_window_title("")  # restore default terminal title
        sys.stdout.write("\n\n")
        stats["wall_time"] = time.monotonic() - session_start
        write_footer(md_path, stats)

        if stats["chunks"] > 0 and interactive:
            # Flush any Wispr-pasted text that arrived during shutdown
            flush_stdin()
            time.sleep(0.5)
            flush_stdin()
            # Prompt for a real title
            new_title = prompt_title()
            if new_title:
                heading = new_title
                md_path = rename_transcript(md_path, heading)

            # Pick folder for notes
            put(f"{DIM}pick a folder for notes (esc to skip):{RESET}")
            try:
                folder_picker.run(raw_mode=False)
            except (KeyboardInterrupt, EOFError):
                pass

            dest_dir = folder_picker.get_destination()
            if dest_dir:
                generate_notes(md_path, dest_dir, heading,
                               category=folder_picker.category)

        put(f"{DIM}{md_path.name}{RESET}")


if __name__ == "__main__":
    main()
