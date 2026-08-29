"""Tests for the Craft sidebar panel and its wiring into the app.

A fake client is injected by patching CraftClient at the point the mixin
constructs it, so no test touches the network or 1Password. Worker results are
awaited by polling for the visible outcome -- `workers.wait_for_complete()` is
unusable here, since the exclusive preview group cancels superseded workers and
a cancelled worker's `wait()` raises instead of completing.
"""

import time

import pytest

from librarian.config import (
    CalendarConfig,
    Config,
    CraftConfig,
    FoldersConfig,
    IconConfig,
    ObsidianConfig,
    TagConfig,
    ToolsConfig,
)
from librarian.craft import CraftDoc, CraftError, CraftFolder
from librarian.database import add_file, batch_writes
from librarian.widgets import FileList, TagList

DOC = CraftDoc(
    id="D1",
    title="Weekly Sync",
    clickable_link="craftdocs://open?spaceId=S&documentId=OTHER",
)


class FakeCraft:
    """Stands in for CraftClient; records calls, answers instantly."""

    instances: list["FakeCraft"] = []

    def __init__(self, api_url: str, api_key_ref: str) -> None:
        self.api_url = api_url
        self.api_key_ref = api_key_ref
        self.doc_requests: list[str] = []
        FakeCraft.instances.append(self)

    def list_folders(self) -> list[CraftFolder]:
        return [
            CraftFolder(
                id="F1",
                name="meetings",
                document_count=1,
                folders=[CraftFolder(id="F2", name="archive", document_count=0)],
            )
        ]

    def list_documents(self, folder_id: str) -> list[CraftDoc]:
        self.doc_requests.append(folder_id)
        return [DOC] if folder_id == "F1" else []

    def fetch_document_markdown(self, doc_id: str) -> str:
        return self.markdown

    markdown = "## Latest occurrence\n\ndiscussed things"

    def search_tags(self) -> list[tuple[str, int]]:
        return []

    def search_documents_by_tag(self, tag: str) -> list[CraftDoc]:
        return []

    def clear_cache(self) -> None:
        self.cache_cleared = True


class BrokenCraft(FakeCraft):
    def list_folders(self) -> list[CraftFolder]:
        raise CraftError("1Password is locked -- unlock the 1Password app and retry")


async def wait_until(pilot, predicate, timeout: float = 5.0) -> None:
    """Pump the app until `predicate()` holds, or fail.

    Generous timeout: it only matters when something is already broken, and the
    preview debounce alone accounts for 0.15s of legitimate waiting.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        await pilot.pause(0.05)
    raise AssertionError("condition not met before timeout")


@pytest.fixture
def vault(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    (root / "local-note.md").write_text("# local #tagged\n")
    (root / "sub").mkdir()  # somewhere for the folder-tree cursor to land
    return root


@pytest.fixture
def config(vault, tmp_path):
    return Config(
        scan_directory=vault,
        editor="vim",
        taskpaper="",
        tags=TagConfig(),
        export_directory=tmp_path / "exports",
        data_directory=tmp_path / "data",
        calendar=CalendarConfig(),
        craft=CraftConfig(api_url="https://example.test/api/v1", api_key_ref="op://x/y/z"),
        tools=ToolsConfig(craft=True),
        icons=IconConfig(style="nerd"),
        folders=FoldersConfig(),
        obsidian=ObsidianConfig(),
    )


@pytest.fixture
def app(config, tmp_index, monkeypatch):
    from librarian.app import LibrarianApp

    monkeypatch.setattr("librarian.actions.craft_actions.CraftClient", FakeCraft)
    FakeCraft.instances.clear()

    with batch_writes():
        add_file(config.scan_directory / "local-note.md", 1.0, ["tagged"])

    return LibrarianApp(config)


def craft_labels(app) -> list[str]:
    tree = app.query_one(TagList).craft_tree
    return [str(node.label) for node in tree.root.children]


async def focus_and_load(app, pilot) -> None:
    """Focus the Craft panel (which triggers the first fetch) and let it load."""
    tree = app.query_one(TagList).craft_tree
    tree.focus()
    await wait_until(pilot, lambda: craft_labels(app) == ["meetings (1)"])


async def highlight_meetings(app, pilot) -> None:
    """Put the Craft tree cursor on the 'meetings' folder and let docs load.

    The cursor moves by key, as a user's would: assigning `cursor_line` before
    the tree's first layout finds no node at that line and emits no highlight.
    """
    await focus_and_load(app, pilot)
    await pilot.press("down")
    await wait_until(
        pilot,
        lambda: app.query_one(FileList).get_selected_craft_doc() == DOC,
    )


class TestPanel:
    async def test_panel_absent_by_default(self, config, tmp_index):
        from librarian.app import LibrarianApp

        config.tools = ToolsConfig()
        app = LibrarianApp(config)
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            tag_list = app.query_one(TagList)
            assert tag_list.craft_tree is None
            ids = [child.id for child in tag_list.children]
            assert "craft-panel" not in ids

    async def test_panel_sits_between_folders_and_tags(self, app):
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            ids = [child.id for child in app.query_one(TagList).children]
            assert ids == ["folders-panel", "craft-panel", "tags-panel"]

    async def test_client_is_built_from_config(self, app):
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            (client,) = FakeCraft.instances
            assert client.api_url == "https://example.test/api/v1"
            assert client.api_key_ref == "op://x/y/z"

    async def test_nothing_is_fetched_until_the_panel_is_focused(self, app):
        """The fetch runs `op read`; a 1Password prompt at startup for a panel
        never touched is the projection lesson learned once already."""
        async with app.run_test(size=(100, 40)) as pilot:
            for _ in range(6):
                await pilot.pause(0.05)
            assert craft_labels(app) == ["(select to load)"]

    async def test_folders_load_on_first_focus(self, app):
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            await focus_and_load(app, pilot)

    async def test_a_broken_connection_shows_in_the_panel(
        self, config, tmp_index, monkeypatch
    ):
        from librarian.app import LibrarianApp

        monkeypatch.setattr(
            "librarian.actions.craft_actions.CraftClient", BrokenCraft
        )
        app = LibrarianApp(config)
        async with app.run_test(size=(100, 40)) as pilot:
            app.query_one(TagList).craft_tree.focus()
            await wait_until(
                pilot,
                lambda: any("1Password is locked" in l for l in craft_labels(app)),
            )

    async def test_startup_focus_is_still_the_folder_tree(self, app):
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            tag_list = app.query_one(TagList)
            assert app.focused is tag_list.directory_tree

    async def test_loading_folders_does_not_steal_the_files_panel(self, app):
        """Folders arriving must not switch the source away from folders --
        focusing the panel loads the tree, but only a cursor move selects."""
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            await focus_and_load(app, pilot)
            await pilot.pause()
            assert app.query_one(TagList).active_source == "folders"


class TestBrowsing:
    async def test_highlighting_a_folder_lists_its_docs(self, app):
        async with app.run_test(size=(100, 40)) as pilot:
            await highlight_meetings(app, pilot)

            tag_list = app.query_one(TagList)
            assert tag_list.active_source == "craft"

            file_list = app.query_one(FileList)
            assert file_list.get_header_text() == "FILES (craft: meetings)"
            # Remote docs are not files: the file actions must see no selection.
            assert file_list._files == []
            assert file_list.get_selected_file() is None

    async def test_highlighted_doc_previews_its_markdown(self, app):
        async with app.run_test(size=(100, 40)) as pilot:
            await highlight_meetings(app, pilot)

            preview = app.query_one("#preview")
            await wait_until(
                pilot,
                lambda: "Weekly Sync"
                in str(preview.query_one("#preview-header").render()),
            )

    async def test_moving_back_to_the_folder_tree_switches_the_source(self, app):
        async with app.run_test(size=(100, 40)) as pilot:
            await highlight_meetings(app, pilot)

            tag_list = app.query_one(TagList)
            tag_list.directory_tree.focus()
            await pilot.press("down")
            await wait_until(pilot, lambda: tag_list.active_source == "folders")

    async def test_app_refocus_refreshes_an_externally_edited_doc(self, app):
        """Editing the note in Craft.app and coming back must show the edit --
        the cache is dropped and the selected doc refetched on AppFocus."""
        async with app.run_test(size=(100, 40)) as pilot:
            await highlight_meetings(app, pilot)
            preview = app.query_one("#preview")
            await wait_until(
                pilot, lambda: "Latest occurrence" in preview.markdown_widget.source
            )

            app._craft.markdown = "## Edited in Craft"
            app.on_app_focus()
            await wait_until(
                pilot, lambda: "Edited in Craft" in preview.markdown_widget.source
            )
            assert app._craft.cache_cleared

    async def test_e_opens_the_doc_in_craft(self, app, monkeypatch):
        opened = []
        monkeypatch.setattr(
            "librarian.actions.craft_actions.subprocess.Popen",
            lambda args, **kwargs: opened.append(args),
        )
        async with app.run_test(size=(100, 40)) as pilot:
            await highlight_meetings(app, pilot)

            await app.run_action("edit")
            assert opened == [["open", DOC.clickable_link]]

    async def test_e_still_edits_files_outside_craft(self, app, monkeypatch):
        opened = []
        monkeypatch.setattr(
            "librarian.actions.craft_actions.subprocess.Popen",
            lambda args, **kwargs: opened.append(args),
        )
        edited = []

        async def fake_edit(self, path):
            edited.append(path)

        from librarian.actions.file_actions import FileActionsMixin

        monkeypatch.setattr(FileActionsMixin, "_edit_file", fake_edit)

        async with app.run_test(size=(100, 40)) as pilot:
            # Folder view leads at startup; wait for the local note's preview,
            # which is what action_edit edits.
            preview = app.query_one("#preview")
            await wait_until(
                pilot, lambda: preview.get_current_file() is not None
            )

            await app.run_action("edit")
            await pilot.pause()
            assert opened == []
            assert [p.name for p in edited] == ["local-note.md"]


class TestFocusOrder:
    async def test_tab_skips_the_hidden_craft_tree(self, app):
        """Only the active workspace's tree is a stop; Craft's is hidden here."""
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            tag_list = app.query_one(TagList)

            tag_list.directory_tree.focus()
            await pilot.pause()
            app.action_focus_next()
            await pilot.pause()
            assert app.focused is tag_list.all_tags_list_view

    async def test_search_exit_returns_to_the_craft_tree(self, app):
        async with app.run_test(size=(100, 40)) as pilot:
            await highlight_meetings(app, pilot)
            tree = app.query_one(TagList).craft_tree

            app.action_search()
            await pilot.pause()
            await pilot.press("escape")

            await wait_until(pilot, lambda: app.focused is tree)
            # And the doc listing came back after search cleared it.
            await wait_until(
                pilot,
                lambda: app.query_one(FileList).get_selected_craft_doc() == DOC,
            )
