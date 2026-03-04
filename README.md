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

Two things you need first:

1. **[Wispr Flow](https://wispr.com)** — install it and do one test recording so it's set up
2. **[Google Cloud SDK](https://cloud.google.com/sdk/docs/install)** — for Gemini note generation via Vertex AI

Then open **Terminal** (press `Cmd+Space`, type "Terminal", hit Enter) and paste this:

```bash
curl -fsSL https://raw.githubusercontent.com/yashsmehta/wispr-unleashed/main/get.sh | bash
```

The installer checks everything, installs what's needed, and sets up the keyboard shortcut.

> **First time?** After installing the Google Cloud SDK, run this once to log in:
> ```bash
> gcloud auth application-default login
> ```

## Usage

**Option A — Keyboard shortcut** (recommended):

> Press `Option+Shift+W` to start recording.<br>
> Press `Option+Shift+W` again to stop. Pick a folder and notes appear in Obsidian.

**Option B — Terminal:**

```bash
python3 ~/wispr-unleashed/record.py "Meeting Title"
```

Press `Ctrl+C` to stop. Notes are generated automatically.

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

Everything works out of the box. To customize, edit `~/wispr-unleashed/.env`:

| Setting | Default | What it does |
|:---|:---|:---|
| `OBSIDIAN_VAULT` | `~/Desktop/Obsidian Vault` | Where notes are saved |
| `TRANSCRIPTS_DIR` | `$OBSIDIAN_VAULT/Transcripts` | Where raw transcripts go |
| `GEMINI_MODEL` | `gemini-3.1-flash-lite-preview` | AI model for note generation |

## License

MIT
