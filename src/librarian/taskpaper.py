"""Convert taskpaper format to markdown for preview and export."""

import re


# Pattern for @tags like @done, @due(2024-01-01), @priority(high)
_AT_TAG_PATTERN = re.compile(r"@(\w+)(?:\(([^)]*)\))?")


def taskpaper_to_markdown(content: str) -> str:
    """Convert taskpaper content to markdown.

    Conversion rules:
    - Project lines (ending with ':') → ### heading
    - Tasks starting with '- ' → checkbox items
    - @done tasks → checked + strikethrough
    - @tags → rendered in backticks
    - Other lines → plain text
    """
    lines = content.splitlines()
    result = []

    for line in lines:
        stripped = line.strip()

        if not stripped:
            result.append("")
            continue

        # Project: line ending with ':' (not starting with '- ')
        if stripped.endswith(":") and not stripped.startswith("- "):
            project_name = stripped[:-1].strip()
            result.append(f"### {project_name}")
            continue

        # Task: line starting with '- '
        if stripped.startswith("- "):
            task_text = stripped[2:]
            is_done = bool(re.search(r"@done\b", task_text))

            # Remove @done (with optional value) from display text
            task_text = re.sub(r"\s*@done(?:\([^)]*\))?\s*", " ", task_text).strip()

            # Replace remaining @tags with backtick-highlighted versions
            task_text = _AT_TAG_PATTERN.sub(_format_at_tag, task_text)

            if is_done:
                result.append(f"- [x] ~~{task_text}~~")
            else:
                result.append(f"- [ ] {task_text}")
            continue

        # Note / plain text — still highlight @tags
        formatted = _AT_TAG_PATTERN.sub(_format_at_tag, stripped)
        result.append(formatted)

    return "\n".join(result)


def _format_at_tag(match: re.Match) -> str:
    """Format an @tag match as backtick-highlighted text."""
    tag_name = match.group(1)
    tag_value = match.group(2)
    if tag_value is not None:
        return f"`@{tag_name}({tag_value})`"
    return f"`@{tag_name}`"
