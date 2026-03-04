# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Wispr Clawd is a macOS tool that records meeting audio using [Wispr Flow](https://wispr.com) and produces transcribed markdown files. It works around Wispr Flow's 6-minute recording limit by cycling recording chunks automatically, polling Wispr's SQLite database for completed transcriptions, and stitching them into a single markdown file. After recording ends, it calls the Gemini API to generate dense meeting notes from the transcript.

## Key Commands

```bash
# Record a meeting (runs until Ctrl+C or 2-hour limit)
python3 record.py "Meeting Title"

# Install macOS keyboard shortcut (Option+Shift+W) via Automator Quick Action
bash setup.sh

# Toggle recording on/off (used by the keyboard shortcut)
bash toggle.sh
```

## Architecture

**`record.py`** — Core recording loop:
- Cycles Wispr Flow hands-free recording in ~4m40s chunks (before the 6-min hard limit)
- Polls `~/Library/Application Support/Wispr Flow/flow.sqlite` (read-only) for new transcriptions
- Appends each chunk to a timestamped markdown file in `TRANSCRIPTS_DIR`
- On shutdown: drains in-flight transcription, writes session summary footer, then calls Gemini API to generate meeting notes saved as a separate file in the user's Obsidian vault
- Interactive folder picker lets you choose an Obsidian category/subfolder for the generated notes
- Uses a PID file at `/tmp/wispr-clawd.pid` for toggle coordination

**`toggle.sh`** — Keyboard shortcut handler: if recording is running (PID file exists), sends SIGINT to stop; otherwise prompts for a meeting title via `osascript` dialog and starts `record.py` in the background.

**`setup.sh`** — Installs an Automator Quick Action (`~/Library/Services/Wispr Clawd.workflow/`) so the user can bind Option+Shift+W to toggle recording.

## Configuration

All configuration is via environment variables (`.env` file loaded automatically):

| Variable | Default | Description |
|---|---|---|
| `GOOGLE_API_KEY` | *(required)* | Google AI Studio API key for note generation |
| `OBSIDIAN_VAULT` | `~/Documents/Obsidian Vault` | Path to Obsidian vault (for note output and folder picker) |
| `TRANSCRIPTS_DIR` | `$OBSIDIAN_VAULT/Transcripts` | Where raw transcript files are saved |
| `GEMINI_MODEL` | `gemini-3-flash-preview` | Gemini model to use for note generation |

## Important Details

- Wispr Flow must be installed and used at least once (so the SQLite DB exists)
- A `GOOGLE_API_KEY` is required for auto-generated meeting notes (get one at [Google AI Studio](https://aistudio.google.com/apikey))
- Transcriptions are matched by `transcriptEntityId` to avoid duplicates; the `known_ids` set tracks already-processed chunks
- Signal handling: first Ctrl+C triggers graceful shutdown with drain; second forces exit
- Category-aware prompts: meetings get a "meeting notes" prompt; talks/lectures/seminars get a "talk notes" prompt
- Transcript files go to `TRANSCRIPTS_DIR` with format `YYYY-MM-DD-slug.md`
