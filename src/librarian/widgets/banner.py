"""Custom ASCII art banner widget replacing the default Textual Header."""

from rich.text import Text

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

# Rows of the robot mark, echoing the Nerd Font `md-robot` glyph used for
# folders: an antenna ball above a head with two eyes and small ears either
# side, on a flat base. Three rows, so the banner stays short.
ROBOT_ROWS = (
    "  ●  ",
    "╢● ●╟",
    " ▀▀▀ ",
)

ROBOT_WIDTH = max(len(row) for row in ROBOT_ROWS)

TITLE = "LIBRARIAN"
SUBTITLE = "Terminal Notes & Tasks"
URL = "github.com/7robots/librarian"

# One color per letter of the title, cycled from the same palette the folder
# icons use.
TITLE_COLORS = (
    "bright_cyan",
    "bright_green",
    "bright_yellow",
    "bright_magenta",
    "bright_red",
)

ANTENNA_COLOR = "bright_green"
EYE_COLOR = "bright_white"
BODY_COLOR = "bright_cyan"


def _append_robot_row(text: Text, row: str, is_antenna_row: bool = False) -> None:
    """Append one row of the robot, colored per character."""
    for char in row:
        if char == "●":
            # Same glyph serves as antenna and eyes; the row decides the color.
            style = ANTENNA_COLOR if is_antenna_row else EYE_COLOR
            text.append(char, style=f"bold {style}")
        elif char in "╢╟▀":
            text.append(char, style=f"bold {BODY_COLOR}")
        else:
            text.append(char)


def _append_title(text: Text) -> None:
    """Append the title, one color per letter, spaced for presence."""
    for index, letter in enumerate(TITLE):
        text.append(letter, style=f"bold {TITLE_COLORS[index % len(TITLE_COLORS)]}")
        if index < len(TITLE) - 1:
            text.append(" ")


def _build_banner() -> Text:
    """Build the banner: robot mark on the left, title and tagline beside it."""
    text = Text(no_wrap=True)
    gap = "  "

    for index, row in enumerate(ROBOT_ROWS):
        _append_robot_row(text, row.ljust(ROBOT_WIDTH), is_antenna_row=index == 0)
        text.append(gap)

        if index == 1:
            _append_title(text)
        elif index == 2:
            text.append(SUBTITLE, style="bright_white")
            text.append("  │  ", style="dim")
            text.append(URL, style="italic cyan")

        if index < len(ROBOT_ROWS) - 1:
            text.append("\n")

    return text


class Banner(Vertical):
    """Application banner with a compact robot mark and title."""

    DEFAULT_CSS = """
    Banner {
        width: 100%;
        height: 3;
        background: $primary-background;
        padding: 0 1;
    }

    Banner > #banner-art {
        width: 100%;
        height: 3;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(_build_banner(), id="banner-art")
