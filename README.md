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

## Install

You need **[Wispr Flow](https://wispr.com)** installed (do one test recording so it's set up).

Then open **Terminal** (press `Cmd+Space`, type "Terminal", hit Enter) and paste:

```bash
curl -fsSL https://raw.githubusercontent.com/yashsmehta/wispr-unleashed/main/scripts/get.sh | bash
```

The installer walks you through everything — dependencies, API credentials, and keyboard shortcut.

### Gemini setup

The installer will ask how you want to authenticate. Pick one:

**Option A — API key** (recommended, simplest):

1. Get a free key at [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
2. The installer will prompt you to paste it, or add it to `~/wispr-unleashed/.env` manually:
   ```
   GOOGLE_API_KEY=your-key-here
   ```

**Option B — Vertex AI** (Google Cloud SDK):

1. Install the [Google Cloud SDK](https://cloud.google.com/sdk/docs/install)
2. Run `gcloud auth application-default login`
3. Set in `.env`:
   ```
   GOOGLE_GENAI_USE_VERTEXAI=True
   ```

## Usage

The installer adds a `wispr` command to your shell. Just run:

```bash
wispr "Meeting Title"
```

Press `Ctrl+C` to stop. You'll be prompted to pick a folder, then notes are generated automatically.

## How It Works

<p align="center">
  <img src="assets/diagram.png" alt="Recording pipeline" width="100%">
</p>

1. Opens Wispr Flow hands-free recording
2. Every 5 minutes, silently cycles to a new chunk (staying under the 6-min limit)
3. Stitches transcriptions into a single markdown file
4. On stop, sends the full transcript to Gemini and saves structured notes to your Obsidian vault

Notes adapt to what you're recording — save to a project folder and you get detailed action items alongside your notes; save to **Talks** or **Lectures** and you get structured academic notes without action items.

## Configuration

Edit `~/wispr-unleashed/.env` to customize:

| Setting | Default | What it does |
|:---|:---|:---|
| `GOOGLE_API_KEY` | — | Gemini API key ([get one here](https://aistudio.google.com/apikey)) |
| `GOOGLE_GENAI_USE_VERTEXAI` | `False` | Use Vertex AI instead of API key |
| `GEMINI_MODEL` | `gemini-3.1-flash-lite-preview` | Gemini model for note generation |
| `OBSIDIAN_VAULT` | `~/Desktop/Obsidian Vault` | Where notes are saved |
| `TRANSCRIPTS_DIR` | `$OBSIDIAN_VAULT/Transcripts` | Where raw transcripts go |
| `USER_NAME` | — | Your name (used for context in note generation) |

### Customizing prompts

The prompt templates that control how notes are generated live in `~/wispr-unleashed/prompts/`:

| File | Used for |
|:---|:---|
| `meeting_notes.md` | Structured meeting notes |
| `action_items.md` | Action item extraction |
| `talk_notes.md` | Talk, lecture, and seminar notes |

Edit these to change the style, structure, or detail level of your notes. Since you always get the full transcript saved to `TRANSCRIPTS_DIR`, you can re-run note generation or tweak prompts and try again — the raw transcript is never lost.

## License

MIT
