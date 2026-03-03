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
import selectors
import signal
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

# ── Constants ────────────────────────────────────────────────────────────────

WISPR_DB = Path.home() / "Library" / "Application Support" / "Wispr Flow" / "flow.sqlite"
MEETINGS_DIR = Path(__file__).resolve().parent / "meetings"
PID_FILE = Path("/tmp/wispr-clawd.pid")
POLL_INTERVAL = 5        # seconds between DB polls while recording
POLL_FAST = 1            # seconds between DB polls while waiting for transcription
RECORD_DURATION = 350    # 5m50s — stop before Wispr's 6-min hard limit
PROCESS_TIMEOUT = 30     # seconds to wait for transcription after stopping
MAX_DURATION = 60 * 60   # 1 hour hard limit
DRAIN_TIMEOUT = 15       # seconds to wait for in-flight chunk after Ctrl+C
INPUT_TIMEOUT = 5 * 60   # auto-generate notes after 5 min of no response

NOTES_PROMPT = """\
You are processing a raw meeting transcript. Generate extremely information-dense meeting notes.

Rules:
- Extract every concrete fact, decision, number, name, deadline, action item, and technical detail
- Use terse bullet points — no filler words, no "the team discussed", no summaries of summaries
- Group by topic, not by chronological order
- If someone committed to doing something, mark it as an action item with their name
- If a decision was made, state the decision directly
- If a question was raised but not resolved, note it as an open question
- Preserve specific numbers, dates, URLs, code references, and proper nouns exactly
- Skip pleasantries, greetings, off-topic chatter, and repetition
- Be brutally concise — every word must carry information

Output format (markdown):
## Key Decisions
## Action Items
## Discussion Notes (grouped by topic)
## Open Questions
"""

# ── Terminal formatting ──────────────────────────────────────────────────────

DIM = "\033[2m"
BOLD = "\033[1m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RESET = "\033[0m"


def put(msg: str):
    """Print a line, clearing any Wispr-pasted text first."""
    sys.stdout.write(f"\033[2K\r  {msg}\n")
    sys.stdout.flush()


# ── Helpers ──────────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return re.sub(r"-+", "-", text).strip("-")


def create_markdown_file(heading: str) -> Path:
    MEETINGS_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    slug = slugify(heading)
    base = MEETINGS_DIR / f"{date_str}-{slug}.md"

    path = base
    counter = 2
    while path.exists():
        path = MEETINGS_DIR / f"{date_str}-{slug}-{counter}.md"
        counter += 1

    now = datetime.now()
    path.write_text(
        f"# {heading}\n\n"
        f"**Date**: {now.strftime('%A, %B %-d, %Y')}\n"
        f"**Started**: {now.strftime('%-I:%M %p')}\n\n"
        f"---\n\n"
    )
    return path


def start_recording():
    subprocess.run(["open", "wispr-flow://start-hands-free"], check=False)


def stop_recording():
    subprocess.run(["open", "wispr-flow://stop-hands-free"], check=False)


def get_utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.000 +00:00")


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


def append_chunk(md_path: Path, chunk: dict, chunk_num: int):
    time_label = datetime.now().strftime("%-I:%M %p")
    with open(md_path, "a") as f:
        f.write(f"### [{time_label}] Chunk {chunk_num}\n\n")
        f.write(chunk["text"].strip() + "\n\n")


def accept_chunk(result: dict, md_path: Path, known_ids: set, stats: dict):
    chunk_num = stats["chunks"] + 1
    known_ids.add(result["id"])
    append_chunk(md_path, result, chunk_num)
    stats["chunks"] += 1
    stats["words"] += result["numWords"]
    stats["recording_time"] += result["duration"]
    return chunk_num


def write_footer(md_path: Path, stats: dict):
    end_time = datetime.now().strftime("%-I:%M %p")
    total_minutes = int(stats["wall_time"] // 60)
    rec_minutes = int(stats["recording_time"] // 60)
    rec_seconds = int(stats["recording_time"] % 60)
    with open(md_path, "a") as f:
        f.write("---\n\n")
        f.write("## Session Summary\n\n")
        f.write(f"- **Ended**: {end_time}\n")
        f.write(f"- **Total duration**: {total_minutes} minutes\n")
        f.write(f"- **Recording time**: {rec_minutes}m {rec_seconds:02d}s ({stats['chunks']} chunks)\n")
        f.write(f"- **Total words**: {stats['words']:,}\n")


def notify(message: str):
    subprocess.run(
        ["osascript", "-e", f'display notification "{message}" with title "Wispr"'],
        check=False,
    )


def open_in_obsidian(file_path: Path):
    vault = "Obsidian Vault"
    vault_relative = f"Meeting Transcripts/{file_path.name}"
    uri = f"obsidian://open?vault={quote(vault)}&file={quote(vault_relative)}"
    subprocess.run(["open", uri], check=False)


def generate_notes(md_path: Path):
    put(f"{DIM}generating notes...{RESET}")

    transcript = md_path.read_text()
    env = {k: v for k, v in os.environ.items()
           if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")}
    result = subprocess.run(
        ["claude", "-p", "--output-format", "text",
         NOTES_PROMPT + "\n\nTRANSCRIPT:\n" + transcript],
        capture_output=True, text=True, timeout=300, env=env,
    )

    if result.returncode != 0 or not result.stdout.strip():
        put(f"{YELLOW}notes generation failed{RESET}")
        return

    notes = result.stdout.strip()
    with open(md_path, "a") as f:
        f.write("\n---\n\n## Meeting Notes (auto-generated)\n\n")
        f.write(notes + "\n")

    put(f"{GREEN}✓{RESET} notes added {DIM}({len(notes.split())}w){RESET}")


def prompt_with_timeout(timeout: int) -> str:
    sel = selectors.DefaultSelector()
    sel.register(sys.stdin, selectors.EVENT_READ)
    ready = sel.select(timeout=timeout)
    sel.close()
    if ready:
        try:
            return sys.stdin.readline().strip().lower()
        except EOFError:
            return ""
    return ""


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Usage: wispr <meeting title>")
        sys.exit(1)

    heading = sys.argv[1]

    if not WISPR_DB.exists():
        print("Wispr Flow not found. Is it installed?")
        sys.exit(1)

    PID_FILE.write_text(str(os.getpid()))
    atexit.register(lambda: PID_FILE.unlink(missing_ok=True))

    shutdown_requested = False
    force_exit = False
    chunk_in_flight = False
    md_path = create_markdown_file(heading)
    open_in_obsidian(md_path)
    known_ids: set = set()
    stats = {"chunks": 0, "words": 0, "recording_time": 0.0, "wall_time": 0.0}
    session_start = time.monotonic()

    def handle_sigint(signum, frame):
        nonlocal shutdown_requested, force_exit
        if shutdown_requested:
            force_exit = True
            sys.exit(1)
        shutdown_requested = True
        put(f"\n{DIM}stopping...{RESET}")

    signal.signal(signal.SIGINT, handle_sigint)

    # Header
    print(f"\n  {BOLD}wispr{RESET} {DIM}·{RESET} {heading}\n")

    try:
        while not shutdown_requested:
            if time.monotonic() - session_start >= MAX_DURATION:
                put(f"{YELLOW}1h limit reached{RESET}")
                break

            since_utc = get_utc_now()
            chunk_num = stats["chunks"] + 1
            put(f"{GREEN}●{RESET} recording {DIM}chunk {chunk_num}{RESET}")
            start_recording()
            chunk_in_flight = True

            rec_start = time.monotonic()
            recording_active = True

            while not shutdown_requested:
                time.sleep(POLL_FAST if not recording_active else POLL_INTERVAL)

                result = poll_for_transcription(since_utc, known_ids)
                if result:
                    chunk_in_flight = False
                    n = accept_chunk(result, md_path, known_ids, stats)
                    put(f"{GREEN}✓{RESET} chunk {n} {DIM}— {result['numWords']}w{RESET}")
                    if recording_active:
                        shutdown_requested = True
                    break

                rec_elapsed = time.monotonic() - rec_start

                if recording_active and rec_elapsed >= RECORD_DURATION:
                    stop_recording()
                    recording_active = False

                if not recording_active and rec_elapsed >= RECORD_DURATION + PROCESS_TIMEOUT:
                    put(f"{YELLOW}timeout — retrying{RESET}")
                    break

        stop_recording()

        if chunk_in_flight and not force_exit:
            drain_start = time.monotonic()
            while time.monotonic() - drain_start < DRAIN_TIMEOUT:
                if force_exit:
                    break
                result = poll_for_transcription(since_utc, known_ids)
                if result:
                    n = accept_chunk(result, md_path, known_ids, stats)
                    put(f"{GREEN}✓{RESET} chunk {n} {DIM}— {result['numWords']}w{RESET}")
                    break
                time.sleep(POLL_FAST)

    finally:
        stats["wall_time"] = time.monotonic() - session_start
        write_footer(md_path, stats)

        rec_min = int(stats["recording_time"] // 60)
        rec_sec = int(stats["recording_time"] % 60)
        put(f"{BOLD}done{RESET} {DIM}— {stats['words']:,}w · {stats['chunks']} chunks · {rec_min}m{rec_sec:02d}s{RESET}")

        if stats["chunks"] > 0:
            print(f"\n  generate notes? {BOLD}Y{RESET}/{DIM}n{RESET} ", end="", flush=True)
            answer = prompt_with_timeout(INPUT_TIMEOUT)
            print()
            if answer in ("", "y", "yes"):
                try:
                    generate_notes(md_path)
                except subprocess.TimeoutExpired:
                    put(f"{YELLOW}notes timed out{RESET}")
                except FileNotFoundError:
                    put(f"{YELLOW}claude not found{RESET}")

        put(f"{DIM}{md_path.name}{RESET}")
        notify(f"{stats['words']:,} words · {stats['chunks']} chunks")


if __name__ == "__main__":
    main()
