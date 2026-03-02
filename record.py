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


# ── Helpers ──────────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    """Convert text to a filename-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return re.sub(r"-+", "-", text).strip("-")


def create_markdown_file(heading: str) -> Path:
    """Create the markdown file with a header. Returns the file path."""
    MEETINGS_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    slug = slugify(heading)
    base = MEETINGS_DIR / f"{date_str}-{slug}.md"

    # Handle name collisions
    path = base
    counter = 2
    while path.exists():
        path = MEETINGS_DIR / f"{date_str}-{slug}-{counter}.md"
        counter += 1

    now = datetime.now()
    date_display = now.strftime("%A, %B %-d, %Y")
    time_display = now.strftime("%-I:%M %p")

    path.write_text(
        f"# {heading}\n\n"
        f"**Date**: {date_display}\n"
        f"**Started**: {time_display}\n\n"
        f"---\n\n"
    )
    return path


def start_recording():
    """Trigger Wispr Flow hands-free recording."""
    subprocess.run(["open", "wispr-flow://start-hands-free"], check=False)


def stop_recording():
    """Stop Wispr Flow recording."""
    subprocess.run(["open", "wispr-flow://stop-hands-free"], check=False)


def get_utc_now() -> str:
    """Return current UTC timestamp matching the DB format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.000 +00:00")


def poll_for_transcription(since_utc: str, known_ids: set) -> dict | None:
    """Query Wispr Flow's DB for a new transcription entry.

    Returns a dict with id, text, numWords, duration on success, else None.
    """
    try:
        conn = sqlite3.connect(f"file:{WISPR_DB}?mode=ro", uri=True)
    except sqlite3.OperationalError as e:
        print_status(f"DB read error: {e}")
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
    except sqlite3.OperationalError as e:
        print_status(f"DB read error: {e}")
    finally:
        conn.close()
    return None


def append_chunk(md_path: Path, chunk: dict, chunk_num: int):
    """Append a transcription chunk to the markdown file."""
    time_label = datetime.now().strftime("%-I:%M %p")
    with open(md_path, "a") as f:
        f.write(f"### [{time_label}] Chunk {chunk_num}\n\n")
        f.write(chunk["text"].strip() + "\n\n")


def accept_chunk(result: dict, md_path: Path, known_ids: set, stats: dict, label: str = ""):
    """Process a new transcription result: update stats, append to markdown, log."""
    chunk_num = stats["chunks"] + 1
    known_ids.add(result["id"])
    append_chunk(md_path, result, chunk_num)
    stats["chunks"] += 1
    stats["words"] += result["numWords"]
    stats["recording_time"] += result["duration"]
    print_status(f"Chunk {chunk_num}: {result['numWords']} words{label}")
    return chunk_num


def write_footer(md_path: Path, stats: dict):
    """Write the session summary footer."""
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


def notify(title: str, message: str):
    """Send a macOS notification."""
    subprocess.run(
        ["osascript", "-e", f'display notification "{message}" with title "{title}"'],
        check=False,
    )


def open_in_obsidian(file_path: Path):
    """Open a file in Obsidian via the vault symlink."""
    vault = "Obsidian Vault"
    # File is accessible via "Meeting Transcripts" symlink in the vault
    vault_relative = f"Meeting Transcripts/{file_path.name}"
    uri = f"obsidian://open?vault={quote(vault)}&file={quote(vault_relative)}"
    subprocess.run(["open", uri], check=False)


def generate_notes(md_path: Path):
    """Run claude CLI on the transcript to generate dense meeting notes."""
    print_status("Generating meeting notes with Claude...")
    notify("Wispr Clawd", "Generating meeting notes...")

    transcript = md_path.read_text()

    env = {k: v for k, v in os.environ.items()
           if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")}
    result = subprocess.run(
        ["claude", "-p", "--output-format", "text",
         NOTES_PROMPT + "\n\nTRANSCRIPT:\n" + transcript],
        capture_output=True, text=True, timeout=300, env=env,
    )

    if result.returncode != 0:
        print_status(f"Claude failed (exit {result.returncode}): {result.stderr[:200]}")
        return

    notes = result.stdout.strip()
    if not notes:
        print_status("Claude returned empty output, skipping notes")
        return

    with open(md_path, "a") as f:
        f.write("\n---\n\n")
        f.write("## Meeting Notes (auto-generated)\n\n")
        f.write(notes + "\n")

    print_status(f"Meeting notes appended ({len(notes.split())} words)")


def print_status(msg: str):
    """Print a timestamped status message."""
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 record.py \"Meeting Title\"")
        sys.exit(1)

    heading = sys.argv[1]

    # Verify DB exists
    if not WISPR_DB.exists():
        print(f"Error: Wispr Flow database not found at {WISPR_DB}")
        print("Is Wispr Flow installed and has it been used at least once?")
        sys.exit(1)

    # PID file for toggle.sh
    PID_FILE.write_text(str(os.getpid()))
    atexit.register(lambda: PID_FILE.unlink(missing_ok=True))

    # State
    shutdown_requested = False
    force_exit = False
    md_path = create_markdown_file(heading)
    open_in_obsidian(md_path)
    known_ids: set = set()
    stats = {"chunks": 0, "words": 0, "recording_time": 0.0, "wall_time": 0.0}
    session_start = time.monotonic()

    # Signal handling: first Ctrl+C = graceful, second = force
    def handle_sigint(signum, frame):
        nonlocal shutdown_requested, force_exit
        if shutdown_requested:
            print("\nForce exit.")
            force_exit = True
            sys.exit(1)
        shutdown_requested = True
        print("\n")
        print_status("Shutting down gracefully... (Ctrl+C again to force)")

    signal.signal(signal.SIGINT, handle_sigint)

    print_status(f"Meeting: {heading}")
    print_status(f"Output:  {md_path}")
    print_status(f"Chunk length: {RECORD_DURATION // 60}m {RECORD_DURATION % 60}s")
    print_status("Press Ctrl+C to stop recording\n")

    try:
        while not shutdown_requested:
            # Hard time limit
            elapsed = time.monotonic() - session_start
            if elapsed >= MAX_DURATION:
                print_status("1-hour limit reached. Stopping.")
                break

            # Start a recording chunk
            since_utc = get_utc_now()
            print_status(f"Starting chunk {stats['chunks'] + 1}...")
            start_recording()

            # Poll during recording (every 5s) to catch early stops.
            # After we stop recording, poll fast (every 1s) to detect
            # when Wispr finishes transcribing, then immediately restart.
            rec_start = time.monotonic()
            recording_active = True

            while not shutdown_requested:
                # Poll slowly while recording, fast after stopping
                time.sleep(POLL_FAST if not recording_active else POLL_INTERVAL)

                # Check for new transcription
                result = poll_for_transcription(since_utc, known_ids)
                if result:
                    accept_chunk(result, md_path, known_ids, stats,
                                 f", {result['duration']:.0f}s — restarting")
                    break

                rec_elapsed = time.monotonic() - rec_start

                # Stop recording at our limit (before Wispr's 6-min cutoff)
                if recording_active and rec_elapsed >= RECORD_DURATION:
                    print_status(f"Stopping chunk {stats['chunks'] + 1}, waiting for transcription...")
                    stop_recording()
                    recording_active = False

                # Give up if no transcription arrives after stop + timeout
                if not recording_active and rec_elapsed >= RECORD_DURATION + PROCESS_TIMEOUT:
                    print_status("Warning: no transcription after timeout. Retrying...")
                    break

        # ── Graceful shutdown ────────────────────────────────────────────
        stop_recording()

        # Drain: wait briefly for any in-flight transcription
        print_status("Waiting for any in-flight transcription...")
        drain_start = time.monotonic()
        while time.monotonic() - drain_start < DRAIN_TIMEOUT:
            if force_exit:
                break
            result = poll_for_transcription(since_utc, known_ids)
            if result:
                accept_chunk(result, md_path, known_ids, stats, " (final)")
                break
            time.sleep(POLL_FAST)

    finally:
        stats["wall_time"] = time.monotonic() - session_start
        write_footer(md_path, stats)
        print()
        print_status(f"Recording done! {stats['chunks']} chunks, {stats['words']:,} words")

        # Generate meeting notes from transcript
        if stats["chunks"] > 0:
            try:
                generate_notes(md_path)
            except subprocess.TimeoutExpired:
                print_status("Claude timed out generating notes")
            except FileNotFoundError:
                print_status("claude CLI not found — skipping notes generation")

        print_status(f"Saved to {md_path}")
        notify("Wispr Clawd", f"Done — {stats['chunks']} chunks, {stats['words']:,} words")


if __name__ == "__main__":
    main()
