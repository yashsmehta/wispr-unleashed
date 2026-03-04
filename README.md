<p align="center">
  <img src="assets/banner.png" alt="Wispr Unleashed" width="100%">
</p>

<p align="center">
  <em>Bypass Wispr Flow's 6-minute recording limit. Record for hours. Get structured notes automatically.</em>
</p>

<p align="center">
  <a href="https://wispr.com">Wispr Flow</a> is the best voice-to-text on macOS — but it caps at 6 minutes.<br>
  This tool removes that limit. It silently cycles recordings in 5-minute chunks,<br>
  stitches the transcriptions, and generates structured notes with Gemini.
</p>

---

## Setup

You need [Wispr Flow](https://wispr.com) installed and a free [Google AI Studio API key](https://aistudio.google.com/apikey).

Then open Terminal and run:

```bash
git clone https://github.com/yashsmehta/wispr-unleashed.git
cd wispr-unleashed
bash install.sh
```

The installer walks you through everything — installs dependencies, saves your API key, and optionally sets up a keyboard shortcut.

## Usage

**From Terminal:**

```bash
python3 record.py "Weekly Standup"
# press Ctrl+C to stop → notes are generated automatically
```

**From anywhere** (after setting up the keyboard shortcut):

Press `Option+Shift+W` → type a meeting title → press Start. Press `Option+Shift+W` again to stop and generate notes.

## How It Works

<p align="center">
  <img src="assets/diagram.png" alt="Recording pipeline" width="100%">
</p>

1. Opens Wispr Flow hands-free recording
2. Every 5 minutes, silently cycles to a new chunk (staying under the 6-min limit)
3. Stitches transcriptions into a single markdown file
4. On stop, sends the full transcript to Gemini and saves structured notes to your Obsidian vault

## Note Generation

Notes adapt to what you're recording — the system detects your Obsidian folder structure:

| If you save to... | You get notes optimized for... |
|:---|:---|
| **Meetings** folder | Action items, decisions, key ideas by topic |
| **Talks / Lectures / Seminars** folder | Core argument, methods, results, references |

Output uses Obsidian-flavored markdown with callouts, highlights, LaTeX, and tables.

## Configuration

All optional — the defaults work out of the box. Edit `.env` to customize:

| Variable | Default | Description |
|:---|:---|:---|
| `GOOGLE_API_KEY` | — | Your API key *(set during install)* |
| `OBSIDIAN_VAULT` | `~/Documents/Obsidian Vault` | Path to your Obsidian vault |
| `TRANSCRIPTS_DIR` | `$OBSIDIAN_VAULT/Transcripts` | Where raw transcripts go |
| `GEMINI_MODEL` | `gemini-3-flash-preview` | Gemini model for note generation |

## License

MIT
