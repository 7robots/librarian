"""Tests that the Folders panel renders Notebook Navigator icons and colors."""

import json

import pytest
from rich.cells import cell_len
from textual.app import App, ComposeResult

from librarian.obsidian import PLUGIN_DATA_RELATIVE_PATH, NotebookNavigatorAppearance
from librarian.widgets.tag_list import MarkdownDirectoryTree

VAULT_DATA = {
    "showFolderIcons": True,
    "inheritFolderColors": True,
    "folderIcons": {"techne": "computer", "kybernetes": "emoji:\U0001f916"},
    "folderColors": {"techne": "#6b7280", "kybernetes": "#06b6d4"},
}

LAPTOP = "\U000f0322"  # md-laptop, the nerd glyph for Lucide "computer"
LAPTOP_EMOJI = "\U0001f4bb"  # 💻, the same icon in emoji style
ROBOT = "\U0001f916"  # 🤖, configured as a literal emoji in the vault
NERD_FOLDER = "\U000f024b"  # md-folder, the no-icon default


@pytest.fixture
def vault(tmp_path):
    """A vault with two styled folders, one unstyled folder, and a note."""
    root = tmp_path / "7robots"
    (root / ".obsidian").mkdir(parents=True)
    data_path = root / PLUGIN_DATA_RELATIVE_PATH
    data_path.parent.mkdir(parents=True)
    data_path.write_text(json.dumps(VAULT_DATA))

    (root / "techne").mkdir()
    (root / "kybernetes").mkdir()
    (root / "veritas").mkdir()
    (root / "techne" / "note.md").write_text("# note #ai\n")
    return root


class TreeApp(App):
    """Minimal host app for the directory tree."""

    def __init__(self, path, appearance):
        super().__init__()
        self._path = path
        self._appearance = appearance

    def compose(self) -> ComposeResult:
        yield MarkdownDirectoryTree(
            str(self._path), appearance=self._appearance, id="directory-tree"
        )


async def render_labels(vault, appearance):
    """Expand the tree and return {folder name: rendered label Text}."""
    app = TreeApp(vault, appearance)
    async with app.run_test(size=(60, 20)) as pilot:
        tree = app.query_one("#directory-tree", MarkdownDirectoryTree)
        tree.root.expand()
        await pilot.pause()

        labels = {}
        for node in tree.root.children:
            labels[node.data.path.name] = tree.render_label(
                node, tree.rich_style, tree.rich_style
            )
        return labels


@pytest.mark.asyncio
async def test_lucide_icon_and_color_applied(vault):
    labels = await render_labels(vault, NotebookNavigatorAppearance.load(vault))
    label = labels["techne"]

    assert LAPTOP in label.plain  # md-laptop from the "computer" icon
    assert any(
        span.style.color and span.style.color.triplet.hex == "#6b7280"
        for span in label.spans
        if span.style.color is not None
    )


@pytest.mark.asyncio
async def test_emoji_icon_and_color_applied(vault):
    labels = await render_labels(vault, NotebookNavigatorAppearance.load(vault))
    label = labels["kybernetes"]

    assert ROBOT in label.plain  # passed through verbatim
    assert any(
        span.style.color and span.style.color.triplet.hex == "#06b6d4"
        for span in label.spans
        if span.style.color is not None
    )


@pytest.mark.asyncio
async def test_unstyled_folder_gets_default_glyph_and_no_color(vault):
    labels = await render_labels(vault, NotebookNavigatorAppearance.load(vault))
    label = labels["veritas"]

    assert label.plain.endswith("veritas")
    assert NERD_FOLDER in label.plain  # default, keeps names aligned
    assert LAPTOP not in label.plain
    # Textual's own component styles still color the label; only the vault's
    # configured colors must be absent.
    applied = {
        span.style.color.triplet.hex
        for span in label.spans
        if span.style.color is not None
    }
    assert applied.isdisjoint(VAULT_DATA["folderColors"].values())


@pytest.mark.asyncio
async def test_icon_replaces_the_tree_toggle_glyph(vault):
    """One icon per row: the folder icon sits where the toggle glyph would be."""
    labels = await render_labels(vault, NotebookNavigatorAppearance.load(vault))
    label = labels["techne"]

    assert label.plain.startswith(LAPTOP)  # the icon leads the row
    assert MarkdownDirectoryTree.ICON_NODE not in label.plain
    assert label.plain.count(LAPTOP) == 1


@pytest.mark.asyncio
async def test_icon_carries_the_toggle_meta(vault):
    """Clicking the icon must still expand/collapse the folder."""
    labels = await render_labels(vault, NotebookNavigatorAppearance.load(vault))
    label = labels["techne"]

    icon_span = label.spans[0]
    assert icon_span.start == 0
    assert icon_span.style.meta.get("toggle") is True


@pytest.mark.asyncio
async def test_clicking_icon_expands_folder(vault):
    """End-to-end: a click in the icon cell toggles the node."""
    app = TreeApp(vault, NotebookNavigatorAppearance.load(vault))
    async with app.run_test(size=(60, 20)) as pilot:
        tree = app.query_one("#directory-tree", MarkdownDirectoryTree)
        tree.root.expand()
        await pilot.pause()

        techne = next(
            node for node in tree.root.children if node.data.path.name == "techne"
        )
        assert not techne.is_expanded

        # Find the x of the first cell carrying the toggle meta on techne's row,
        # which is the icon now that it has taken the toggle's place.
        row = techne._line
        x = 0
        for segment in tree.render_line(row):
            if segment.style and segment.style.meta.get("toggle"):
                break
            x += cell_len(segment.text)

        await pilot.click(tree, offset=(x, row))
        await pilot.pause()

        assert techne.is_expanded


@pytest.mark.asyncio
async def test_color_applies_to_icon_and_name(vault):
    """colorIconOnly is false in this vault, so both are tinted."""
    labels = await render_labels(vault, NotebookNavigatorAppearance.load(vault))
    label = labels["techne"]

    def color_at(offset: int) -> str | None:
        hexes = [
            span.style.color.triplet.hex
            for span in label.spans
            if span.style.color is not None and span.start <= offset < span.end
        ]
        return hexes[-1] if hexes else None

    assert color_at(0) == "#6b7280"  # the icon
    assert color_at(label.plain.index("techne")) == "#6b7280"  # the name


@pytest.mark.asyncio
async def test_color_icon_only_leaves_name_untinted(vault):
    appearance = NotebookNavigatorAppearance.load(vault)
    appearance.color_icon_only = True
    labels = await render_labels(vault, appearance)
    label = labels["techne"]

    name_offset = label.plain.index("techne")
    name_colors = {
        span.style.color.triplet.hex
        for span in label.spans
        if span.style.color is not None and span.start <= name_offset < span.end
    }
    assert "#6b7280" not in name_colors


@pytest.mark.asyncio
async def test_emoji_style_renders_emoji_icons(vault):
    """The emoji style is the fallback for terminals without a Nerd Font."""
    labels = await render_labels(vault, NotebookNavigatorAppearance.load(vault, "emoji"))

    assert labels["techne"].plain.startswith(LAPTOP_EMOJI)
    assert LAPTOP not in labels["techne"].plain
    assert labels["kybernetes"].plain.startswith(ROBOT)  # emoji icons are unchanged


@pytest.mark.asyncio
@pytest.mark.parametrize("style", ["nerd", "emoji"])
async def test_names_align_across_icon_widths(vault, style):
    """Every folder name must start in the same column.

    This is the constraint that forces uniform icon padding: a vault can mix
    one-cell Nerd Font glyphs with two-cell emoji in the same tree.
    """
    labels = await render_labels(vault, NotebookNavigatorAppearance.load(vault, style))
    offsets = {
        name: cell_len(label.plain[: label.plain.index(name)])
        for name, label in labels.items()
    }
    assert len(set(offsets.values())) == 1, offsets


@pytest.mark.asyncio
async def test_no_appearance_renders_default_labels(vault):
    """A vault without the plugin (appearance=None) is left untouched."""
    labels = await render_labels(vault, None)
    assert labels["techne"].plain.startswith(MarkdownDirectoryTree.ICON_NODE)
    assert labels["techne"].plain.endswith("techne")
    assert LAPTOP not in labels["techne"].plain


@pytest.mark.asyncio
async def test_setting_appearance_later_applies_it(vault):
    """set_scan_directory assigns appearance after construction."""
    app = TreeApp(vault, None)
    async with app.run_test(size=(60, 20)) as pilot:
        tree = app.query_one("#directory-tree", MarkdownDirectoryTree)
        tree.root.expand()
        await pilot.pause()

        tree.appearance = NotebookNavigatorAppearance.load(vault)
        await pilot.pause()

        techne = next(
            node for node in tree.root.children if node.data.path.name == "techne"
        )
        label = tree.render_label(techne, tree.rich_style, tree.rich_style)
        assert label.plain.startswith(LAPTOP)


@pytest.mark.asyncio
async def test_clearing_appearance_restores_default_toggle(vault):
    """Pointing at a non-vault directory falls back to the stock tree."""
    app = TreeApp(vault, NotebookNavigatorAppearance.load(vault))
    async with app.run_test(size=(60, 20)) as pilot:
        tree = app.query_one("#directory-tree", MarkdownDirectoryTree)
        tree.root.expand()
        await pilot.pause()

        tree.appearance = None
        await pilot.pause()

        techne = next(
            node for node in tree.root.children if node.data.path.name == "techne"
        )
        label = tree.render_label(techne, tree.rich_style, tree.rich_style)
        assert label.plain.startswith(MarkdownDirectoryTree.ICON_NODE)
        assert LAPTOP not in label.plain
