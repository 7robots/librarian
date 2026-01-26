"""Navigation state management for wiki link navigation."""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class NavigationState:
    """Snapshot of file list state for navigation history."""

    tag: str | None
    files: list[Path]
    selected_index: int
    header_text: str


class NavigationStack:
    """Stack-based history for wiki link navigation."""

    def __init__(self) -> None:
        self._stack: list[NavigationState] = []

    def push(self, state: NavigationState) -> None:
        """Push a state onto the navigation stack."""
        self._stack.append(state)

    def pop(self) -> NavigationState | None:
        """Pop and return the most recent state, or None if empty."""
        if self._stack:
            return self._stack.pop()
        return None

    def clear(self) -> None:
        """Clear all navigation history."""
        self._stack.clear()

    def is_empty(self) -> bool:
        """Check if the navigation stack is empty."""
        return len(self._stack) == 0

    def __len__(self) -> int:
        return len(self._stack)
