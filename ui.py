"""Terminal UI components for Wispr Unleashed."""

import os
import select
import sys
import termios
import tty
from pathlib import Path

# ── Terminal formatting ──────────────────────────────────────────────────────

DIM = "\033[2m"
BOLD = "\033[1m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
RESET = "\033[0m"
HIDE_CURSOR = "\033[?25l"
SHOW_CURSOR = "\033[?25h"

DOT_EMPTY = f"{DIM}·{RESET}"
DOT_ACTIVE = f"{YELLOW}●{RESET}"
DOT_DONE = f"{GREEN}●{RESET}"
DOT_COUNT = 10


def put(msg: str):
    """Print a line, clearing any Wispr-pasted text first."""
    sys.stdout.write(f"\033[2K\r  {msg}\n")
    sys.stdout.flush()


def draw_dots(completed: int, active: bool, suffix: str = ""):
    """Draw the dot matrix with optional right-side annotation."""
    total = max(DOT_COUNT, completed + 1)
    dots = []
    for i in range(total):
        if i < completed:
            dots.append(DOT_DONE)
        elif i == completed and active:
            dots.append(DOT_ACTIVE)
        else:
            dots.append(DOT_EMPTY)
    line = " ".join(dots)
    if suffix:
        line += f"  {DIM}{suffix}{RESET}"
    sys.stdout.write(f"\033[2K\r  {line}")
    sys.stdout.flush()


def flush_stdin():
    """Discard any text Wispr pasted into the terminal's input buffer."""
    try:
        termios.tcflush(sys.stdin.fileno(), termios.TCIFLUSH)
    except (termios.error, OSError):
        pass


# ── Interactive menu ─────────────────────────────────────────────────────────

class SelectMenu:
    """Arrow-key navigable menu. Assumes terminal is already in cbreak mode."""

    def __init__(self, items: list[str], prompt: str = ""):
        self.items = items
        self.prompt = prompt
        self.cursor = 0
        self._line_count = 0

    def _render(self):
        lines = []
        if self.prompt:
            lines.append(f"  {DIM}{self.prompt}{RESET}")
        for i, item in enumerate(self.items):
            if i == self.cursor:
                lines.append(f"  {CYAN}›{RESET} {BOLD}{item}{RESET}")
            else:
                lines.append(f"    {DIM}{item}{RESET}")
        lines.append(f"  {DIM}↑↓ enter esc{RESET}")

        sys.stdout.write("".join(f"\033[2K{line}\n" for line in lines))
        sys.stdout.flush()
        self._line_count = len(lines)

    def _erase(self):
        if self._line_count > 0:
            n = self._line_count
            sys.stdout.write(
                f"\033[{n}A" + "\033[2K\n" * n + f"\033[{n}A"
            )
            sys.stdout.flush()
            self._line_count = 0

    def _read_key(self) -> str:
        fd = sys.stdin.fileno()
        ch = os.read(fd, 1)
        if ch == b"\x1b":
            if select.select([fd], [], [], 0.05)[0]:
                ch2 = os.read(fd, 1)
                if ch2 == b"[":
                    ch3 = os.read(fd, 1)
                    return {"A": "up", "B": "down"}.get(ch3.decode(), "")
            return "esc"
        if ch in (b"\r", b"\n"):
            return "enter"
        return ""

    def run(self) -> str | None:
        """Display menu, process arrow keys. Returns selected item or None."""
        flush_stdin()
        sys.stdout.write(HIDE_CURSOR)
        sys.stdout.write("\n")
        self._render()
        try:
            while True:
                key = self._read_key()
                if not key:
                    continue
                self._erase()
                if key == "up":
                    self.cursor = (self.cursor - 1) % len(self.items)
                elif key == "down":
                    self.cursor = (self.cursor + 1) % len(self.items)
                elif key == "enter":
                    return self.items[self.cursor]
                elif key == "esc":
                    return None
                self._render()
        finally:
            self._erase()
            sys.stdout.write(SHOW_CURSOR)
            sys.stdout.flush()


# ── Folder discovery & picker ────────────────────────────────────────────────

def discover_categories(vault_path: Path):
    """Find note category folders in Obsidian vault (excluding Transcripts)."""
    skip = {"transcripts", ".obsidian", ".trash"}
    categories = []
    for p in sorted(vault_path.iterdir()):
        if p.is_dir() and p.name.lower() not in skip and not p.name.startswith("."):
            categories.append(p.name)
    return categories


def discover_subfolders(vault_path: Path, category: str):
    """Find subfolders within a category."""
    cat_dir = vault_path / category
    subs = []
    for p in sorted(cat_dir.iterdir()):
        if p.is_dir() and not p.name.startswith("."):
            subs.append(p.name)
    return subs


class FolderPicker:
    """Two-stage folder selection: category → subfolder."""

    def __init__(self, vault_path: Path):
        self.vault_path = vault_path
        self.category: str | None = None
        self.subfolder: str | None = None
        self.completed = False

    def run(self, raw_mode: bool = False) -> bool:
        """Run the interactive picker. raw_mode=True if terminal is already cbreak."""
        categories = discover_categories(self.vault_path)
        if not categories:
            return False

        fd = sys.stdin.fileno()
        old = None
        if not raw_mode:
            old = termios.tcgetattr(fd)
            tty.setcbreak(fd)
        try:
            menu = SelectMenu(categories, prompt="notes")
            choice = menu.run()
            if choice is None:
                return False
            self.category = choice

            subs = discover_subfolders(self.vault_path, self.category)
            if subs:
                items = subs + ["(root)"]
                menu = SelectMenu(items, prompt=self.category)
                choice = menu.run()
                if choice is not None and choice != "(root)":
                    self.subfolder = choice

            self.completed = True
            return True
        finally:
            if old is not None:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)

    def label(self) -> str:
        if self.completed:
            parts = [self.category]
            if self.subfolder:
                parts.append(self.subfolder)
            return " › ".join(parts)
        return "any key → pick folder"

    def get_destination(self) -> Path | None:
        if not self.completed or not self.category:
            return None
        dest = self.vault_path / self.category
        if self.subfolder:
            dest = dest / self.subfolder
        dest.mkdir(parents=True, exist_ok=True)
        return dest
