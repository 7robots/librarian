"""Type protocols for widget message interfaces.

These protocols define the message types that widgets emit,
enabling type-safe message handling in the app and mixins.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from textual.widgets import ListView


@runtime_checkable
class HasTagSelected(Protocol):
    """Widget that emits TagSelected messages."""

    class TagSelected:
        tag_name: str

    def get_selected_tag(self) -> str | None: ...
    def update_tags(self, tags: list[tuple[str, int]]) -> None: ...


@runtime_checkable
class HasFileHighlighted(Protocol):
    """Widget that emits FileHighlighted messages."""

    class FileHighlighted:
        file_path: Path

    def get_selected_file(self) -> Path | None: ...
    def update_files(
        self,
        files: list[Path],
        tag: str | None = ...,
        navigation_target: str | None = ...,
    ) -> None: ...


@runtime_checkable
class HasMeetingSelected(Protocol):
    """Widget that emits MeetingSelected messages."""

    class MeetingSelected:
        pass

    @property
    def list_view(self) -> ListView: ...


@runtime_checkable
class HasWikiLinkClicked(Protocol):
    """Widget that emits WikiLinkClicked messages."""

    class WikiLinkClicked:
        target: str
        current_file: Path | None

    def get_current_file(self) -> Path | None: ...
