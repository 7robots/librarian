"""Custom ASCII art banner widget replacing the default Textual Header."""

from rich.text import Text

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static


def _build_banner() -> Text:
    """Build the banner as a Rich Text object with per-letter colors."""
    # Letters and their column spans in the 3-row font
    #           L        I      B        R        A        R        I      A        N
    colors = [
        "bright_cyan",
        "bright_green",
        "bright_yellow",
        "bright_magenta",
        "bright_red",
        "bright_cyan",
        "bright_green",
        "bright_yellow",
        "bright_magenta",
    ]
    rows = [
        ["╦  ", "╦", "╔╗ ", "╦═╗", "╔═╗", "╦═╗", "╦", "╔═╗", "╔╗╔"],
        ["║  ", "║", "╠╩╗", "╠╦╝", "╠═╣", "╠╦╝", "║", "╠═╣", "║║║"],
        ["╩═╝", "╩", "╚═╝", "╩╚═", "╩ ╩", "╩╚═", "╩", "╩ ╩", "╝╚╝"],
    ]

    text = Text()
    for row in rows:
        for part, color in zip(row, colors):
            text.append(part, style=f"bold {color}")
        text.append("\n")
    text.append("Markdown Tag Browser", style="bright_white")
    text.append("  │  ", style="dim")
    text.append("github.com/7robots/librarian", style="italic cyan")
    return text


class Banner(Vertical):
    """Application banner with ASCII art title."""

    DEFAULT_CSS = """
    Banner {
        width: 100%;
        height: 5;
        background: $primary-background;
        padding: 0 1;
    }

    Banner > #banner-art {
        width: 100%;
        height: auto;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(_build_banner(), id="banner-art")
