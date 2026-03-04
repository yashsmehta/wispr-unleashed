<p align="center">
  <img src="assets/banner.png" alt="Wispr Unleashed" width="100%">
</p>

<h1 align="center">Wispr Unleashed</h1>

<p align="center">
  <em>Bypass Wispr Flow's 6-minute limit. Record hours of meetings, get structured notes automatically.</em>
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> &bull;
  <a href="#how-it-works">How It Works</a> &bull;
  <a href="#configuration">Configuration</a> &bull;
  <a href="#keyboard-shortcut">Keyboard Shortcut</a>
</p>

---

[Wispr Flow](https://wispr.com) is the best voice-to-text tool on macOS — but it caps recordings at 6 minutes. **Wispr Unleashed** removes that limit by automatically cycling recordings, stitching transcriptions together, and generating structured notes with Gemini when you're done.

Hit `Option+Shift+W` to start. Hit it again to stop. Your notes appear in Obsidian, organized by topic.

## Quick Start

```bash
git clone https://github.com/yashsmehta/wispr-unleashed.git
cd wispr-unleashed
pip install python-dotenv google-genai

cp .env.example .env
# Add your Google AI Studio API key to .env
```

Then record a meeting:

```bash
python3 record.py "Weekly Standup"
```

Press `Ctrl+C` when done — notes are generated automatically.

## Prerequisites

- **macOS** (uses AppleScript and macOS URL schemes)
- **[Wispr Flow](https://wispr.com)** — installed and used at least once
- **Python 3.10+**
- **Google AI Studio API key** — free at [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
- **Obsidian** *(optional)* — for the folder picker and vault integration

## How It Works

```
┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐     ┌──────────┐
│  Start   │────▶│  Record │────▶│  Cycle  │────▶│  Stop   │────▶│ Generate │
│ Wispr    │     │ ~4m40s  │     │ chunks  │     │ Ctrl+C  │     │ notes    │
└─────────┘     └─────────┘     └─────────┘     └─────────┘     └──────────┘
```

1. **Start** — opens Wispr Flow's hands-free recording via URL scheme
2. **Record** — captures audio in ~4m40s chunks, cycling before the 6-min hard limit
3. **Capture** — polls Wispr's SQLite database for completed transcriptions, appends each chunk to a timestamped markdown file
4. **Stop** (`Ctrl+C`) — drains the last in-flight chunk, writes a session footer
5. **Generate** — sends the full transcript to Gemini with a category-aware prompt (meetings vs. talks/lectures), saves structured notes to your chosen Obsidian folder

## Keyboard Shortcut

Set up a global `Option+Shift+W` hotkey to toggle recording on/off:

```bash
bash setup.sh
```

Then go to **System Settings > Keyboard > Keyboard Shortcuts > Services** and assign `Option+Shift+W` to "Wispr Unleashed".

Once set up, one keypress starts recording with a title prompt. Another keypress stops it and generates notes.

## Configuration

All settings via environment variables in `.env`:

| Variable | Default | Description |
|---|---|---|
| `GOOGLE_API_KEY` | *(required)* | Google AI Studio API key |
| `OBSIDIAN_VAULT` | `~/Documents/Obsidian Vault` | Path to your Obsidian vault |
| `TRANSCRIPTS_DIR` | `$OBSIDIAN_VAULT/Transcripts` | Where raw transcripts are saved |
| `GEMINI_MODEL` | `gemini-3-flash-preview` | Gemini model for note generation |

## Note Generation

Wispr Unleashed uses category-aware prompts:

- **Meetings** — extracts action items, decisions, key ideas grouped by topic
- **Talks / Lectures / Seminars** — captures the core argument, methods, results, and references

Notes are written in Obsidian-flavored markdown with callouts, highlights, LaTeX, and tables where appropriate.

## Security Note

If you previously committed a `.env` file with an API key, **revoke the key** at [Google AI Studio](https://aistudio.google.com/apikey) and generate a new one. The `.env` file is gitignored and will not be tracked.

## License

MIT
