<p align="center">
  <img src="assets/banner.png" alt="Wispr Unleashed" width="100%">
</p>

<h1 align="center">Wispr Unleashed</h1>

<p align="center">
  <em>Bypass Wispr Flow's 6-minute recording limit. Record for hours. Get structured notes automatically.</em>
</p>

<p align="center">
  <a href="https://wispr.com">Wispr Flow</a> is the best voice-to-text on macOS — but it caps at 6 minutes.<br>
  This tool removes the limit by silently cycling recordings in 5-minute chunks,<br>
  stitching transcriptions, and generating notes with Gemini when you stop.
</p>

<br>

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

<br>

## How It Works

<table>
<tr>
<td width="50%">

**The recording loop:**

1. Opens Wispr Flow hands-free recording
2. Every 5 minutes, silently cycles to a new chunk
3. Polls Wispr's database for completed transcriptions
4. Stitches chunks into a single timestamped markdown file

**When you stop** (`Ctrl+C`):

5. Drains the last in-flight transcription
6. Sends the full transcript to Gemini
7. Saves structured notes to your Obsidian vault

</td>
<td width="50%">

```
  ┌──────────────────────────────┐
  │     Wispr Flow (recording)   │
  │  ┌─────┐ ┌─────┐ ┌─────┐   │
  │  │ 5m  │→│ 5m  │→│ 5m  │→… │
  │  └──┬──┘ └──┬──┘ └──┬──┘   │
  └─────┼───────┼───────┼──────┘
        ↓       ↓       ↓
  ┌─────────────────────────────┐
  │   Transcript (stitched md)  │
  └──────────────┬──────────────┘
                 ↓
  ┌─────────────────────────────┐
  │   Gemini → Structured Notes │
  └─────────────────────────────┘
```

</td>
</tr>
</table>

<br>

## Keyboard Shortcut

Set up `Option+Shift+W` to toggle recording from anywhere:

```bash
bash setup.sh
```

Then in **System Settings > Keyboard > Keyboard Shortcuts > Services**, assign the shortcut to "Wispr Unleashed".

One press starts recording (prompts for a title). Another press stops and generates notes.

<br>

## Note Generation

Notes are generated with **category-aware prompts** — the system detects your Obsidian folder structure and adapts:

| Category | Optimized for |
|:---|:---|
| **Meetings** | Action items, decisions, key ideas grouped by topic |
| **Talks / Lectures** | Core argument, methods, results, references |
| **Seminars / Classes** | Definitions, frameworks, worked examples |

Output uses Obsidian-flavored markdown: callouts, highlights, LaTeX, and tables where they aid clarity.

<br>

## Configuration

All settings via `.env`:

| Variable | Default | Description |
|:---|:---|:---|
| `GOOGLE_API_KEY` | — | Google AI Studio API key *(required)* |
| `OBSIDIAN_VAULT` | `~/Documents/Obsidian Vault` | Path to your Obsidian vault |
| `TRANSCRIPTS_DIR` | `$OBSIDIAN_VAULT/Transcripts` | Where raw transcripts go |
| `GEMINI_MODEL` | `gemini-3-flash-preview` | Model for note generation |

<br>

## Prerequisites

- **macOS** — uses AppleScript and URL schemes
- **[Wispr Flow](https://wispr.com)** — installed and used at least once
- **Python 3.10+**
- **[Google AI Studio API key](https://aistudio.google.com/apikey)** — free tier available
- **Obsidian** *(optional)* — for folder picker and vault integration

<br>

## License

MIT
