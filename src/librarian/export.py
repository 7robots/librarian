"""Export markdown files to PDF or HTML."""

from pathlib import Path

import markdown


# CSS styling for exported documents
EXPORT_CSS = """
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    line-height: 1.6;
    max-width: 800px;
    margin: 0 auto;
    padding: 2rem;
    color: #333;
}

h1, h2, h3, h4, h5, h6 {
    margin-top: 1.5em;
    margin-bottom: 0.5em;
    font-weight: 600;
}

h1 { font-size: 2em; border-bottom: 1px solid #eee; padding-bottom: 0.3em; }
h2 { font-size: 1.5em; border-bottom: 1px solid #eee; padding-bottom: 0.3em; }
h3 { font-size: 1.25em; }

code {
    background-color: #f6f8fa;
    padding: 0.2em 0.4em;
    border-radius: 3px;
    font-family: "SF Mono", Consolas, "Liberation Mono", Menlo, monospace;
    font-size: 0.9em;
}

pre {
    background-color: #f6f8fa;
    padding: 1em;
    border-radius: 6px;
    overflow-x: auto;
}

pre code {
    background: none;
    padding: 0;
}

blockquote {
    border-left: 4px solid #ddd;
    margin: 0;
    padding-left: 1em;
    color: #666;
}

a {
    color: #0366d6;
    text-decoration: none;
}

a:hover {
    text-decoration: underline;
}

table {
    border-collapse: collapse;
    width: 100%;
    margin: 1em 0;
}

th, td {
    border: 1px solid #ddd;
    padding: 0.5em;
    text-align: left;
}

th {
    background-color: #f6f8fa;
}

img {
    max-width: 100%;
}

hr {
    border: none;
    border-top: 1px solid #eee;
    margin: 2em 0;
}
"""


def markdown_to_html(content: str, title: str = "Document") -> str:
    """Convert markdown content to a complete HTML document.

    Args:
        content: Markdown content
        title: Document title

    Returns:
        Complete HTML document string
    """
    # Convert markdown to HTML
    md = markdown.Markdown(
        extensions=[
            "fenced_code",
            "tables",
            "toc",
            "nl2br",
        ]
    )
    html_body = md.convert(content)

    # Build complete HTML document
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
{EXPORT_CSS}
    </style>
</head>
<body>
{html_body}
</body>
</html>
"""
    return html


def export_to_html(source_path: Path, export_dir: Path) -> Path:
    """Export a markdown file to HTML.

    Args:
        source_path: Path to the markdown file
        export_dir: Directory to export to

    Returns:
        Path to the exported HTML file
    """
    # Read markdown content
    content = source_path.read_text(encoding="utf-8")

    # Convert to HTML
    title = source_path.stem
    html = markdown_to_html(content, title)

    # Write HTML file
    export_dir.mkdir(parents=True, exist_ok=True)
    output_path = export_dir / f"{source_path.stem}.html"
    output_path.write_text(html, encoding="utf-8")

    return output_path


def export_to_pdf(source_path: Path, export_dir: Path) -> Path:
    """Export a markdown file to PDF using weasyprint.

    Args:
        source_path: Path to the markdown file
        export_dir: Directory to export to

    Returns:
        Path to the exported PDF file

    Raises:
        ImportError: If weasyprint is not installed
    """
    try:
        from weasyprint import HTML
    except ImportError:
        raise ImportError(
            "weasyprint is required for PDF export. "
            "Install with: pip install 'librarian[pdf]'"
        )

    # Read markdown content
    content = source_path.read_text(encoding="utf-8")

    # Convert to HTML
    title = source_path.stem
    html = markdown_to_html(content, title)

    # Convert HTML to PDF
    export_dir.mkdir(parents=True, exist_ok=True)
    output_path = export_dir / f"{source_path.stem}.pdf"

    HTML(string=html).write_pdf(output_path)

    return output_path


def export_markdown(
    source_path: Path,
    export_dir: Path,
    prefer_pdf: bool = True,
) -> tuple[Path, str]:
    """Export a markdown file to PDF or HTML.

    Attempts PDF export first if prefer_pdf is True, falls back to HTML
    if weasyprint is not available.

    Args:
        source_path: Path to the markdown file
        export_dir: Directory to export to
        prefer_pdf: Whether to prefer PDF over HTML

    Returns:
        Tuple of (output_path, format) where format is "pdf" or "html"
    """
    if prefer_pdf:
        try:
            output_path = export_to_pdf(source_path, export_dir)
            return output_path, "pdf"
        except ImportError:
            # Fall back to HTML
            pass

    output_path = export_to_html(source_path, export_dir)
    return output_path, "html"
