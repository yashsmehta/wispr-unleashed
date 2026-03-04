# Wispr Clawd

Record meetings on macOS using [Wispr Flow](https://wispr.com) and automatically generate structured notes with Gemini. Wispr Flow has a 6-minute recording limit — this tool works around it by cycling chunks automatically, stitching transcriptions together, and producing a clean markdown file. When you stop recording, it calls the Gemini API to generate dense, organized notes saved to your Obsidian vault (or any directory).

## Prerequisites

- **macOS** (uses AppleScript and macOS URL schemes)
- **[Wispr Flow](https://wispr.com)** — installed and used at least once (so its SQLite DB exists)
- **Python 3.10+**
- **Google AI Studio API key** — get one free at [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
- **Obsidian** *(optional)* — for the folder picker and vault integration

## Quick Start

```bash
git clone https://github.com/yourusername/wispr-clawd.git
cd wispr-clawd
pip install python-dotenv google-genai

cp .env.example .env
# Edit .env and add your GOOGLE_API_KEY

python3 record.py "Weekly Standup"
# Press Ctrl+C to stop — notes are generated automatically
```

## Keyboard Shortcut

Set up a global hotkey (Option+Shift+W) to toggle recording on/off:

```bash
bash setup.sh
```

Then go to **System Settings → Keyboard → Keyboard Shortcuts → Services** and assign `Option+Shift+W` to "Wispr Clawd".

## Configuration

All settings are via environment variables in `.env`:

| Variable | Default | Description |
|---|---|---|
| `GOOGLE_API_KEY` | *(required)* | Google AI Studio API key |
| `OBSIDIAN_VAULT` | `~/Documents/Obsidian Vault` | Path to Obsidian vault |
| `TRANSCRIPTS_DIR` | `$OBSIDIAN_VAULT/Transcripts` | Where raw transcripts are saved |
| `GEMINI_MODEL` | `gemini-3-flash-preview` | Gemini model for note generation |

## How It Works

1. **Start** — opens Wispr Flow's hands-free recording via URL scheme
2. **Cycle** — every ~4m40s, stops and restarts recording to stay under Wispr's 6-min limit
3. **Capture** — polls Wispr's SQLite database for completed transcriptions, appends each chunk to a timestamped markdown file
4. **Stop** (Ctrl+C) — drains the last in-flight chunk, writes a session footer
5. **Generate** — sends the full transcript to Gemini with a category-aware prompt, saves structured notes to your chosen Obsidian folder

## Security Note

If you previously committed a `.env` file with an API key, **revoke the key** at [Google AI Studio](https://aistudio.google.com/apikey) and generate a new one. The `.env` file is gitignored and will not be tracked.

## License

MIT
