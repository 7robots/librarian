"""Wiki link preprocessing utilities."""

import re
from urllib.parse import quote, unquote

# Pattern to match wiki links: [[target]] or [[target|display text]]
WIKI_LINK_PATTERN = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")

# Scheme used for wiki links in converted markdown
WIKI_LINK_SCHEME = "wikilink:"


def preprocess_wiki_links(content: str) -> str:
    """Convert wiki links to markdown links with wikilink: scheme.

    Converts:
        [[note.md]] -> [note.md](wikilink:note.md)
        [[second test]] -> [second test](wikilink:second%20test)
        [[note|Display Text]] -> [Display Text](wikilink:note)
    """

    def replace_wiki_link(match: re.Match) -> str:
        target = match.group(1).strip()
        display = match.group(2)
        if display:
            display = display.strip()
        else:
            display = target
        # URL-encode the target to handle spaces and special characters
        encoded_target = quote(target, safe="")
        return f"[{display}]({WIKI_LINK_SCHEME}{encoded_target})"

    return WIKI_LINK_PATTERN.sub(replace_wiki_link, content)


def is_wiki_link(href: str) -> bool:
    """Check if a href is a wiki link (uses wikilink: scheme)."""
    return href.startswith(WIKI_LINK_SCHEME)


def extract_wiki_target(href: str) -> str:
    """Extract the target from a wiki link href.

    Args:
        href: A wiki link href like "wikilink:note.md" or "wikilink:second%20test"

    Returns:
        The target, e.g., "note.md" or "second test" (URL-decoded)
    """
    if not is_wiki_link(href):
        return href
    encoded_target = href[len(WIKI_LINK_SCHEME) :]
    # URL-decode to restore spaces and special characters
    return unquote(encoded_target)
