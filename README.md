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
2. **[Google AI Studio API key](https://aistudio.google.com/apikey)** — free, takes 30 seconds to create

Then open **Terminal** (press `Cmd+Space`, type "Terminal", hit Enter) and paste this:

```bash
curl -fsSL https://raw.githubusercontent.com/yashsmehta/wispr-unleashed/main/get.sh | bash
```

The installer checks everything, installs what's needed, asks for your API key, and sets up the keyboard shortcut. It takes about a minute.

## Usage

**Option A — Keyboard shortcut** (recommended):

> Press `Option+Shift+W` → type a title → hit Start.<br>
> Press `Option+Shift+W` again to stop. Notes appear in Obsidian.

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
| `GOOGLE_API_KEY` | — | Your API key *(set during install)* |
| `OBSIDIAN_VAULT` | `~/Desktop/Obsidian Vault` | Where notes are saved |
| `TRANSCRIPTS_DIR` | `$OBSIDIAN_VAULT/Transcripts` | Where raw transcripts go |
| `GEMINI_MODEL` | `gemini-3.1-flash-lite-preview` | AI model for note generation |

## License

MIT
