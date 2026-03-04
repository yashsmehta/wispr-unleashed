# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Wispr Unleashed is a macOS tool that records meeting audio using [Wispr Flow](https://wispr.com) and produces transcribed markdown files. It works around Wispr Flow's 6-minute recording limit by cycling recording chunks automatically (~4m55s each), polling Wispr's SQLite database for completed transcriptions, and stitching them into a single markdown file. After recording ends, it calls the Gemini API to generate dense meeting notes from the transcript.

## Key Commands

```bash
# Record a meeting (runs until Ctrl+C or 2-hour limit)
python3 record.py

# Record with a specific title (otherwise defaults to timestamp)
python3 record.py "Meeting Title"

# Install macOS keyboard shortcut (Option+Shift+W) via Automator Quick Action
bash setup.sh

# Toggle recording on/off (used by the keyboard shortcut)
bash toggle.sh

# One-command install
bash install.sh
```

## Architecture

**`record.py`** — Core recording loop:
- Cycles Wispr Flow hands-free recording in ~4m55s chunks (`RECORD_DURATION = 295`)
- Polls `~/Library/Application Support/Wispr Flow/flow.sqlite` (read-only) for new transcriptions
- Appends each chunk to a timestamped markdown file in `TRANSCRIPTS_DIR`
- Sets terminal window title to `wispr-recording` so `focus_terminal()` can target the correct window via AppleScript (prevents Wispr paste going to wrong terminal)
- On shutdown: drains in-flight transcription, writes session summary footer
- Post-recording interactive flow: prompt for title → folder picker → Gemini note generation
- Notes are saved as `{num:02d} {Title}.md` with YAML `date:` frontmatter in the chosen Obsidian folder
- Auto-numbers notes sequentially within each folder
- Category-aware prompts: meetings get a "meeting notes" prompt; talks/lectures/seminars get a "talk notes" prompt
- Prompts include user's `Glossary.md` (known terms) — new technical terms are flagged in a `> [!study] New Terms` callout
- Uses `USER_NAME` env var to correctly attribute action items to the recorder
- Uses a PID file at `/tmp/wispr-unleashed.pid` for toggle coordination

**`toggle.sh`** — Keyboard shortcut handler: if recording is running (PID file exists), sends SIGINT to stop; otherwise opens a new Terminal window and starts `record.py`.

**`setup.sh`** — Installs an Automator Quick Action (`~/Library/Services/Wispr Unleashed.workflow/`) so the user can bind Option+Shift+W to toggle recording. Generates both `Info.plist` and `document.wflow`, then flushes the macOS services cache.

**`install.sh`** — Interactive installer: checks Python, checks Wispr Flow, installs pip deps, prompts for API key, optionally runs `setup.sh`.

## Configuration

All configuration is via environment variables (`.env` file loaded automatically):

| Variable | Default | Description |
|---|---|---|
| `GOOGLE_API_KEY` | *(required)* | Google AI Studio API key for note generation |
| `USER_NAME` | *(empty)* | Your name — used for action item attribution in notes |
| `OBSIDIAN_VAULT` | `~/Documents/Obsidian Vault` | Path to Obsidian vault (for note output and folder picker) |
| `TRANSCRIPTS_DIR` | `$OBSIDIAN_VAULT/Transcripts` | Where raw transcript files are saved |
| `GEMINI_MODEL` | `gemini-3-flash-preview` | Gemini model to use for note generation |

## Important Details

- Wispr Flow must be installed and used at least once (so the SQLite DB exists)
- A `GOOGLE_API_KEY` is required for auto-generated meeting notes (get one at [Google AI Studio](https://aistudio.google.com/apikey))
- Transcriptions are matched by `transcriptEntityId` to avoid duplicates; the `known_ids` set tracks already-processed chunks
- Signal handling: first Ctrl+C triggers graceful shutdown with drain; second forces exit
- Arrow key input in the folder picker uses `os.read(fd, 1)` directly (not `sys.stdin.read`) to avoid Python's `BufferedReader` consuming escape sequence bytes before `select.select` can detect them
- Transcript files go to `TRANSCRIPTS_DIR` with format `YYYY-MM-DD-slug.md`
- Notes files go to the chosen Obsidian folder with format `{num:02d} {Title}.md`
- `Glossary.md` in the Obsidian vault root tracks known technical terms; new terms from transcripts are flagged in notes
