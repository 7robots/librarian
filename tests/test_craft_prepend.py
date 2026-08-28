"""Tests for the Craft prepend flow: client positioning and the `a` action."""

import json
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
from librarian.craft import CraftClient, CraftDoc, CraftError, CraftFolder, is_tag_line
from librarian.widgets import FileList, TagList

# ---------------------------------------------------------------------------
# Client: where the insert lands
# ---------------------------------------------------------------------------

BLOCKS_WITH_TAG = json.dumps(
    {
        "id": "DOC",
        "content": [
            {"id": "B1", "markdown": "#meetings"},
            {"id": "B2", "markdown": "## 2026-08-21"},
        ],
    }
)

BLOCKS_NO_TAG = json.dumps(
    {
        "id": "DOC",
        "content": [
            {"id": "B1", "markdown": "## 2026-08-21"},
        ],
    }
)

BLOCKS_EMPTY = json.dumps({"id": "DOC", "content": []})


def recording_client(blocks_json: str) -> CraftClient:
    """A client whose transport is canned and records every call."""
    client = CraftClient("https://example.test/api/v1", "op://x/y/z")
    client._calls = []

    def fake_request(path, accept="application/json", method="GET", body=None):
        client._calls.append((method, path, body))
        if path.startswith("/blocks?") and method == "GET":
            return blocks_json
        if path == "/blocks" and method == "POST":
            return '{"items": []}'
        raise AssertionError(f"unexpected {method} {path}")

    client._request = fake_request
    return client


def posted(client) -> dict:
    posts = [c for c in client._calls if c[0] == "POST"]
    assert len(posts) == 1
    return posts[0][2]


class TestIsTagLine:
    def test_single_tag(self):
        assert is_tag_line("#meetings")

    def test_several_tags(self):
        assert is_tag_line("#meetings #q3")

    def test_whitespace_tolerated(self):
        assert is_tag_line("  #meetings  ")

    def test_heading_is_not_a_tag(self):
        assert not is_tag_line("# Heading")

    def test_prose_with_a_tag_is_not_a_tag_line(self):
        assert not is_tag_line("see #meetings for details")

    def test_numeric_fragment_is_not_a_tag(self):
        assert not is_tag_line("#123")

    def test_empty_is_not_a_tag_line(self):
        assert not is_tag_line("")


class TestPrependPosition:
    def test_tag_first_block_anchors_after_it(self):
        client = recording_client(BLOCKS_WITH_TAG)
        client.prepend_markdown("DOC", "## new\n\nbody")
        body = posted(client)
        assert body["position"] == {"position": "after", "siblingId": "B1"}
        assert body["markdown"] == "## new\n\nbody"

    def test_plain_first_block_goes_to_start(self):
        client = recording_client(BLOCKS_NO_TAG)
        client.prepend_markdown("DOC", "x")
        assert posted(client)["position"] == {"position": "start", "pageId": "DOC"}

    def test_empty_document_goes_to_start(self):
        client = recording_client(BLOCKS_EMPTY)
        client.prepend_markdown("DOC", "x")
        assert posted(client)["position"] == {"position": "start", "pageId": "DOC"}

    def test_missing_doc_id_refuses_to_send(self):
        """The API silently routes an unanchored insert into today's daily
        note, so a missing id must fail before any request is made."""
        client = recording_client(BLOCKS_EMPTY)
        with pytest.raises(CraftError, match="refusing to send"):
            client.prepend_markdown("", "x")
        assert client._calls == []

    def test_prepend_invalidates_the_cached_preview(self):
        client = recording_client(BLOCKS_WITH_TAG)
        # Prime the markdown cache; the canned body parses as plain markdown.
        client._cache["md:DOC"] = (time.monotonic(), "stale")
        client.prepend_markdown("DOC", "x")
        assert "md:DOC" not in client._cache

    def test_block_listing_is_never_cached(self):
        """A stale first-block id would anchor the insert on a gone block."""
        client = recording_client(BLOCKS_WITH_TAG)
        client.prepend_markdown("DOC", "x")
        client.prepend_markdown("DOC", "y")
        gets = [c for c in client._calls if c[0] == "GET"]
        assert len(gets) == 2


# ---------------------------------------------------------------------------
# UI: the `a` action
# ---------------------------------------------------------------------------

DOC = CraftDoc(id="D1", title="Weekly Sync", clickable_link="craftdocs://x")


class FakeCraft:
    def __init__(self, api_url: str, api_key_ref: str) -> None:
        self.prepends: list[tuple[str, str]] = []

    def list_folders(self) -> list[CraftFolder]:
        return [CraftFolder(id="F1", name="meetings", document_count=1)]

    def list_documents(self, folder_id: str) -> list[CraftDoc]:
        return [DOC]

    def fetch_document_markdown(self, doc_id: str) -> str:
        return "## old occurrence"

    def prepend_markdown(self, doc_id: str, markdown: str) -> None:
        self.prepends.append((doc_id, markdown))

    def search_tags(self) -> list[tuple[str, int]]:
        return []

    def search_documents_by_tag(self, tag: str) -> list[CraftDoc]:
        return []

    def clear_cache(self) -> None:
        pass


class FakeSuspend:
    """Stands in for App.suspend(), recording that it was entered."""

    def __init__(self):
        self.entered = False

    def __call__(self):
        return self

    def __enter__(self):
        self.entered = True

    def __exit__(self, *args):
        return False


async def wait_until(pilot, predicate, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        await pilot.pause(0.05)
    raise AssertionError("condition not met before timeout")


@pytest.fixture
def config(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "note.md").write_text("# note\n")
    return Config(
        scan_directory=vault,
        editor="true",  # /usr/bin/true: an editor that leaves the buffer alone
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
    return LibrarianApp(config)


async def select_craft_doc(app, pilot) -> None:
    # Let startup finish first: its queued FolderHighlighted would otherwise
    # land after the Craft selection and flip the source back to folders.
    file_list = app.query_one(FileList)
    await wait_until(pilot, lambda: file_list._files)

    # Focusing the panel triggers the first fetch; the cursor then moves by
    # key, as a user's would -- assigning cursor_line before the tree's first
    # layout finds no node at that line and emits nothing.
    tree = app.query_one(TagList).craft_tree
    tree.focus()
    await wait_until(
        pilot,
        lambda: any("meetings" in str(n.label) for n in tree.root.children),
    )
    await pilot.press("down")
    await wait_until(pilot, lambda: file_list.get_selected_craft_doc() == DOC)


def editor_stub(monkeypatch, write: str | None):
    """Replace the editor subprocess; `write` replaces the buffer, None keeps it."""
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        if write is not None:
            from pathlib import Path

            Path(args[1]).write_text(write, encoding="utf-8")

    monkeypatch.setattr(
        "librarian.actions.craft_actions.subprocess.run", fake_run
    )
    return calls


class TestAddOccurrence:
    async def test_edited_buffer_is_prepended(self, app, monkeypatch):
        suspend = FakeSuspend()
        monkeypatch.setattr(app, "suspend", suspend)
        editor_calls = editor_stub(monkeypatch, "## 2026-08-28\n\nnew notes\n")

        async with app.run_test(size=(100, 40)) as pilot:
            await select_craft_doc(app, pilot)
            await pilot.press("a")
            await wait_until(pilot, lambda: app._craft.prepends)

            assert suspend.entered
            assert len(editor_calls) == 1
            assert app._craft.prepends == [
                ("D1", "## 2026-08-28\n\nnew notes\n")
            ]

    async def test_untouched_buffer_sends_nothing(self, app, monkeypatch):
        monkeypatch.setattr(app, "suspend", FakeSuspend())
        editor_stub(monkeypatch, None)

        async with app.run_test(size=(100, 40)) as pilot:
            await select_craft_doc(app, pilot)
            await pilot.press("a")
            await pilot.pause(0.3)

            assert app._craft.prepends == []

    async def test_emptied_buffer_sends_nothing(self, app, monkeypatch):
        monkeypatch.setattr(app, "suspend", FakeSuspend())
        editor_stub(monkeypatch, "  \n")

        async with app.run_test(size=(100, 40)) as pilot:
            await select_craft_doc(app, pilot)
            await pilot.press("a")
            await pilot.pause(0.3)

            assert app._craft.prepends == []

    async def test_a_outside_craft_does_not_open_the_editor(self, app, monkeypatch):
        monkeypatch.setattr(app, "suspend", FakeSuspend())
        editor_calls = editor_stub(monkeypatch, "anything")

        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()  # folder view is active; no Craft doc selected
            await pilot.press("a")
            await pilot.pause(0.3)

            assert editor_calls == []
            assert app._craft.prepends == []

    async def test_success_refreshes_the_preview(self, app, monkeypatch):
        monkeypatch.setattr(app, "suspend", FakeSuspend())
        editor_stub(monkeypatch, "## fresh\n")

        refreshed = []
        from librarian.app import LibrarianApp

        orig = LibrarianApp._do_craft_preview
        monkeypatch.setattr(
            LibrarianApp,
            "_do_craft_preview",
            lambda self, doc: (refreshed.append(doc.id), orig(self, doc)),
        )

        async with app.run_test(size=(100, 40)) as pilot:
            await select_craft_doc(app, pilot)
            refreshed.clear()  # highlights during setup also refresh
            await pilot.press("a")
            await wait_until(pilot, lambda: "D1" in refreshed)
