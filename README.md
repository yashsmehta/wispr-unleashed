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

## Quick Start

```bash
git clone https://github.com/yashsmehta/wispr-unleashed.git
cd wispr-unleashed
pip install python-dotenv google-genai
```

Get a free API key from [Google AI Studio](https://aistudio.google.com/apikey), then:

```bash
cp .env.example .env
# paste your GOOGLE_API_KEY into .env

python3 record.py "Weekly Standup"
# Ctrl+C to stop → notes generated automatically
```

## How It Works

<p align="center">
  <img src="assets/diagram.png" alt="Recording pipeline" width="100%">
</p>

1. Opens Wispr Flow hands-free recording via URL scheme
2. Every 5 minutes, silently stops and restarts — cycling chunks before the 6-min limit
3. Polls Wispr's SQLite database for completed transcriptions, stitches them into a single markdown file
4. On `Ctrl+C`, drains the last in-flight chunk and sends the full transcript to Gemini
5. Saves structured notes to your chosen Obsidian folder

## Keyboard Shortcut

Set up `Option+Shift+W` to toggle recording from anywhere:

```bash
bash setup.sh
```

Then in **System Settings > Keyboard > Keyboard Shortcuts > Services**, assign the shortcut to "Wispr Unleashed".

One press starts recording (prompts for a title). Another press stops and generates notes.

## Note Generation

Notes are generated with **category-aware prompts** — the system detects your Obsidian folder structure and adapts:

| Category | Optimized for |
|:---|:---|
| **Meetings** | Action items, decisions, key ideas grouped by topic |
| **Talks / Lectures / Seminars** | Core argument, methods, results, references, worked examples |

Output uses Obsidian-flavored markdown: callouts, highlights, LaTeX, and tables where they aid clarity.

## Configuration

All settings via `.env`:

| Variable | Default | Description |
|:---|:---|:---|
| `GOOGLE_API_KEY` | — | Google AI Studio API key *(required)* |
| `OBSIDIAN_VAULT` | `~/Documents/Obsidian Vault` | Path to your Obsidian vault |
| `TRANSCRIPTS_DIR` | `$OBSIDIAN_VAULT/Transcripts` | Where raw transcripts go |
| `GEMINI_MODEL` | `gemini-3-flash-preview` | Model for note generation |

## Prerequisites

- **macOS** — uses AppleScript and URL schemes
- **[Wispr Flow](https://wispr.com)** — installed and used at least once
- **Python 3.10+**
- **[Google AI Studio API key](https://aistudio.google.com/apikey)** — free tier available
- **Obsidian** *(optional)* — for folder picker and vault integration

## License

MIT
