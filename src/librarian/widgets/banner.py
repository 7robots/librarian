"""Custom ASCII art banner widget replacing the default Textual Header."""

from rich.text import Text

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static


def _build_banner() -> Text:
    """Build the banner as a Rich Text object with title and book art side by side."""
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
    title_rows = [
        ["╦  ", "╦", "╔╗ ", "╦═╗", "╔═╗", "╦═╗", "╦", "╔═╗", "╔╗╔"],
        ["║  ", "║", "╠╩╗", "╠╦╝", "╠═╣", "╠╦╝", "║", "╠═╣", "║║║"],
        ["╩═╝", "╩", "╚═╝", "╩╚═", "╩ ╩", "╩╚═", "╩", "╩ ╩", "╝╚╝"],
    ]

    # ASCII art: small robot holding a book (placed left of title)
    art_rows = [
        " ┌●●┐ ╔═╗ ",
        " ├──┤─╢≡║ ",
        "  ┘└  ╚═╝ ",
    ]

    robot_color = "bright_cyan"
    eye_color = "bright_green"
    book_color = "bright_yellow"
    text_color = "grey70"

    def _colorize_art(txt: Text, line: str) -> None:
        """Append a single art line with per-character coloring."""
        for ch in line:
            if ch == "●":
                txt.append(ch, style=f"bold {eye_color}")
            elif ch in "╔╗╚╝║╢":
                txt.append(ch, style=f"bold {book_color}")
            elif ch == "≡":
                txt.append(ch, style=text_color)
            elif ch in "┌┐└┘│┬├┤╭╮╰╯┴═╧─":
                txt.append(ch, style=f"bold {robot_color}")
            else:
                txt.append(ch, style="default")

    text = Text()

    # Title on left, art on right, both vertically centered
    max_rows = max(len(title_rows), len(art_rows))
    title_width = sum(len(p) for p in title_rows[0]) if title_rows else 0
    title_voffset = (max_rows - len(title_rows)) // 2
    art_voffset = (max_rows - len(art_rows)) // 2
    gap = " " * 4

    for i in range(max_rows):
        # Title portion (left, vertically centered)
        title_i = i - title_voffset
        if 0 <= title_i < len(title_rows):
            for part, color in zip(title_rows[title_i], colors):
                text.append(part, style=f"bold {color}")
        else:
            text.append(" " * title_width, style="default")

        text.append(gap, style="default")

        # Art portion (right, vertically centered)
        art_i = i - art_voffset
        if 0 <= art_i < len(art_rows):
            _colorize_art(text, art_rows[art_i])

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
