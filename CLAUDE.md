# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Wispr Unleashed is a macOS tool that records meeting audio using [Wispr Flow](https://wispr.com) and produces transcribed markdown files saved directly to Obsidian. It works around Wispr Flow's 6-minute recording limit by cycling recording chunks automatically (~4m55s each), polling Wispr's SQLite database for completed transcriptions, and stitching them into a single markdown file. After recording ends, it sends the transcript to an LLM (any provider via litellm) to generate structured meeting notes (two separate LLM calls: one for notes, one for action items).

## Key Commands

```bash
# Record a meeting (runs until Ctrl+C or 2-hour limit)
wispr

# Record with a specific title (otherwise defaults to timestamp)
wispr "Meeting Title"

# One-command install
bash scripts/install.sh
```

## Architecture

**`record.py`** — Core recording loop and file I/O:
- Cycles Wispr Flow hands-free recording in ~4m55s chunks (`RECORD_DURATION = 295`)
- Polls `~/Library/Application Support/Wispr Flow/flow.sqlite` (read-only) for new transcriptions
- Appends each chunk to a timestamped markdown file in `TRANSCRIPTS_DIR`
- Sets terminal window title to `wispr-recording` so `focus_terminal()` can target the correct window via AppleScript (prevents Wispr paste going to wrong terminal)
- On shutdown: drains in-flight transcription, writes session summary footer
- Post-recording interactive flow: prompt for title → folder picker → note generation via `llm.py`
- Notes are saved as `{num:02d} {Title}.md` with YAML `date:` frontmatter in the chosen Obsidian folder
- Auto-numbers notes sequentially within each folder
- Uses a PID file at `/tmp/wispr-unleashed.pid` for toggle coordination

**`ui.py`** — Terminal UI components:
- ANSI formatting constants (`DIM`, `BOLD`, `GREEN`, `YELLOW`, `CYAN`, `RESET`, etc.)
- `put(msg)` — prints a line with cursor-clearing (handles Wispr-pasted text)
- `draw_dots(completed, active, suffix)` — dot matrix progress indicator
- `flush_stdin()` — discards buffered terminal input
- `SelectMenu` — arrow-key navigable menu (cbreak mode)
- `FolderPicker(vault_path)` — two-stage category → subfolder selection
- `discover_categories(vault_path)` / `discover_subfolders(vault_path, category)` — Obsidian vault folder discovery
- All vault-path-dependent functions take `vault_path` as a parameter (no config imports)

**`llm.py`** — LLM calls for note generation (provider-agnostic via litellm):
- Two parallel API calls per meeting: one for structured notes, one for action items (via `ThreadPoolExecutor`)
- Talks/lectures get a single notes call (no action items)
- Category-aware prompts: meetings get a "meeting notes" prompt; talks/lectures/seminars get a "talk notes" prompt
- Action items are unattributed project tasks (no person assignment) — specific and detailed
- Prompts include user's `Glossary.md` (known terms) — new technical terms are flagged in a `> [!study] New Terms` callout
- Uses `litellm.completion()` — supports any provider (OpenAI, Anthropic, Google, etc.) via `LLM_MODEL` env var

**`prompts/`** — LLM prompt templates (markdown files):
- `meeting_notes.md` — structured meeting notes prompt
- `action_items.md` — action item extraction prompt
- `talk_notes.md` — talk/lecture notes prompt
- Loaded by `llm._read_prompt(name)` with `@lru_cache`

**`scripts/`** — Shell scripts for installation and OS integration:
- `toggle.sh` — Keyboard shortcut handler: if recording is running (PID file exists), sends SIGINT to stop; otherwise opens a new Terminal window and starts `record.py`
- `setup.sh` — Installs an Automator Quick Action (`~/Library/Services/Wispr Unleashed.workflow/`) so the user can bind Option+Shift+W to toggle recording. Generates both `Info.plist` and `document.wflow`, then flushes the macOS services cache
- `install.sh` — Interactive installer: checks Python, checks Wispr Flow, installs pip deps, configures LLM provider in `.env`, optionally adds `wispr` shell command
- `get.sh` — Remote one-liner installer (`curl | bash`): downloads the repo zip, extracts to `~/wispr-unleashed`, and runs `install.sh`

## Configuration

All configuration is via environment variables (`.env` file loaded automatically):

| Variable | Default | Description |
|---|---|---|
| `LLM_MODEL` | `gemini/gemini-2.0-flash` | Model for note generation (any litellm-supported model) |
| `OPENAI_API_KEY` | *(empty)* | For OpenAI models |
| `ANTHROPIC_API_KEY` | *(empty)* | For Anthropic models |
| `GOOGLE_API_KEY` | *(empty)* | For Gemini models |
| `GOOGLE_GENAI_USE_VERTEXAI` | `False` | Set `True` to use Vertex AI with GCP credentials |
| `USER_NAME` | *(empty)* | Your name — used in note generation context |
| `OBSIDIAN_VAULT` | `~/Desktop/Obsidian Vault` | Path to Obsidian vault (for note output and folder picker) |
| `TRANSCRIPTS_DIR` | `$OBSIDIAN_VAULT/Transcripts` | Where raw transcript files are saved |

## Important Details

- Wispr Flow must be installed and used at least once (so the SQLite DB exists)
- Note generation requires an LLM API key in `.env` — any provider supported by litellm (OpenAI, Anthropic, Google, etc.)
- Transcriptions are matched by `transcriptEntityId` to avoid duplicates; the `known_ids` set tracks already-processed chunks
- Signal handling: first Ctrl+C triggers graceful shutdown with drain; second forces exit
- Arrow key input in the folder picker (`ui.py`) uses `os.read(fd, 1)` directly (not `sys.stdin.read`) to avoid Python's `BufferedReader` consuming escape sequence bytes before `select.select` can detect them
- Transcript files go to `TRANSCRIPTS_DIR` with format `YYYY-MM-DD-slug.md`
- Notes files go to the chosen Obsidian folder with format `{num:02d} {Title}.md`
- `Glossary.md` in the Obsidian vault root tracks known technical terms; new terms from transcripts are flagged in notes
