"""Tests for Craft tags: client discovery/listing, and the source-scoped panel."""

import json
import time
import urllib.error
from io import BytesIO

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
from librarian.craft import (
    CraftClient,
    CraftDoc,
    CraftError,
    CraftFolder,
    _retry_delay,
)
from librarian.database import add_file, batch_writes
from librarian.widgets import FileList, TagList

# Snippets as the live API returns them: matched regions bolded as **...**,
# unmatched context elided as "..." -- including the case that broke the first
# implementation, where the match's leading whitespace sits inside the bold.
SEARCH_ALL = json.dumps(
    {
        "items": [
            {"documentId": "D1", "markdown": "agentic iam meetings**\n#meetings**\n..."},
            {"documentId": "D1", "markdown": "...risk (possibly )**\n#arete**"},
            {"documentId": "D2", "markdown": "**#meetings**\n..."},
            {"documentId": "D3", "markdown": "notes** #Meetings**"},  # casing dupe
            {"documentId": None, "markdown": "** #arete**"},
        ]
    }
)

SEARCH_MEETINGS = json.dumps(
    {
        "items": [
            {"documentId": "D1", "markdown": "**#meetings**", "lastModifiedAt": "2026-08-28"},
            {"documentId": "D1", "markdown": "again"},  # dupe doc collapses
            {"documentId": "D2", "markdown": "**#meetings**", "lastModifiedAt": "2026-08-01"},
        ]
    }
)

FOLDER_DOCS = json.dumps(
    {
        "items": [
            {
                "id": "D1",
                "title": "TPS Cabinet",
                "clickableLink": "craftdocs://open?spaceId=S&documentId=OTHER",
            }
        ]
    }
)

CONNECTION = json.dumps(
    {"urlTemplates": {"app": "craftdocs://open?spaceId=S&blockId={blockId}"}}
)

TITLE_D1 = json.dumps({"id": "D1", "type": "page", "markdown": "TPS Cabinet"})
TITLE_D2 = json.dumps({"id": "D2", "type": "page", "markdown": "Patricia 1-1"})


def client_with(responses: dict[str, str]) -> CraftClient:
    client = CraftClient("https://example.test/api/v1", "op://x/y/z")
    client._calls = []

    def fake_request(path, accept="application/json", method="GET", body=None):
        client._calls.append((method, path))
        for prefix, body_text in responses.items():
            if path.startswith(prefix):
                return body_text
        raise AssertionError(f"unexpected {method} {path}")

    client._request = fake_request
    return client


class TestSearchTags:
    def client(self) -> CraftClient:
        return client_with({"/documents/search": SEARCH_ALL})

    def test_tags_extract_from_bolded_snippets(self):
        tags = dict(self.client().search_tags())
        assert "meetings" in tags
        assert "arete" in tags

    def test_counts_are_unique_documents(self):
        # D1 and D2 (and D3 as a casing dupe) carry #meetings; D1 and the
        # null-id item carry #arete.
        tags = dict(self.client().search_tags())
        assert tags["meetings"] == 3

    def test_casing_dedupes_keeping_first_seen(self):
        names = [name for name, _ in self.client().search_tags()]
        assert "meetings" in names
        assert "Meetings" not in names

    def test_sorted_by_count_then_name(self):
        tags = self.client().search_tags()
        counts = [count for _, count in tags]
        assert counts == sorted(counts, reverse=True)

    def test_discovery_is_cached(self):
        client = self.client()
        client.search_tags()
        client.search_tags()
        assert len(client._calls) == 1


class TestSearchDocumentsByTag:
    def client(self) -> CraftClient:
        return client_with(
            {
                "/documents/search": SEARCH_MEETINGS,
                "/documents?": FOLDER_DOCS,
                "/connection": CONNECTION,
                "/blocks?id=D1": TITLE_D1,
                "/blocks?id=D2": TITLE_D2,
            }
        )

    def test_docs_dedupe_and_keep_api_order(self):
        client = self.client()
        docs = client.search_documents_by_tag("meetings")
        assert [d.id for d in docs] == ["D1", "D2"]

    def test_cached_folder_listings_supply_title_and_real_link(self):
        client = self.client()
        client.list_documents("F1")  # browsing warmed this listing
        docs = client.search_documents_by_tag("meetings")
        assert docs[0].title == "TPS Cabinet"
        assert "documentId=OTHER" in docs[0].clickable_link
        # D1 needed no title request.
        assert not any("/blocks?id=D1" in path for _, path in client._calls)

    def test_unknown_docs_resolve_title_and_template_link(self):
        docs = self.client().search_documents_by_tag("meetings")
        d2 = docs[1]
        assert d2.title == "Patricia 1-1"
        assert d2.clickable_link == "craftdocs://open?spaceId=S&blockId=D2"

    def test_a_failing_title_becomes_untitled_not_an_error(self):
        client = client_with(
            {
                "/documents/search": SEARCH_MEETINGS,
                "/connection": CONNECTION,
                "/documents?": FOLDER_DOCS,
            }
        )
        original = client._request

        def flaky(path, **kwargs):
            if path.startswith("/blocks?id="):
                raise CraftError("Craft API: HTTP 502")
            return original(path, **kwargs)

        client._request = flaky
        docs = client.search_documents_by_tag("meetings")
        assert [d.title for d in docs] == ["(untitled)", "(untitled)"]

    def test_tag_is_regex_escaped(self):
        client = self.client()
        client.search_documents_by_tag("c++")  # would explode unescaped in RE2
        search_calls = [p for _, p in client._calls if "/documents/search" in p]
        assert "c%5C%2B%5C%2B" in search_calls[0]  # re.escape('c++') urlencoded


class TestRetry:
    def test_retry_delay_honors_and_clamps_retry_after(self):
        def error_with(retry_after):
            import email.message

            headers = email.message.Message()
            if retry_after is not None:
                headers["Retry-After"] = retry_after
            return urllib.error.HTTPError("u", 429, "too many", headers, BytesIO(b""))

        assert _retry_delay(error_with("3")) == 3.0
        assert _retry_delay(error_with("300")) == 10.0
        assert _retry_delay(error_with(None)) == 1.0
        assert _retry_delay(error_with("soon")) == 1.0

    def test_429_is_retried_once(self, monkeypatch):
        client = CraftClient("https://example.test/api/v1", "op://x/y/z")
        monkeypatch.setattr(
            "librarian.craft.resolve_api_key", lambda ref: "pdk_test"
        )
        monkeypatch.setattr("librarian.craft.time.sleep", lambda s: None)

        attempts = []

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return b'{"items": []}'

        def fake_urlopen(request, timeout=None):
            attempts.append(request.full_url)
            if len(attempts) == 1:
                raise urllib.error.HTTPError(
                    request.full_url, 429, "too many", None, BytesIO(b"")
                )
            return FakeResponse()

        monkeypatch.setattr("librarian.craft.urllib.request.urlopen", fake_urlopen)
        assert client.list_folders() == []
        assert len(attempts) == 2

    def test_a_second_429_is_reported(self, monkeypatch):
        client = CraftClient("https://example.test/api/v1", "op://x/y/z")
        monkeypatch.setattr(
            "librarian.craft.resolve_api_key", lambda ref: "pdk_test"
        )
        monkeypatch.setattr("librarian.craft.time.sleep", lambda s: None)

        def always_429(request, timeout=None):
            raise urllib.error.HTTPError(
                request.full_url, 429, "too many", None, BytesIO(b"")
            )

        monkeypatch.setattr("librarian.craft.urllib.request.urlopen", always_429)
        with pytest.raises(CraftError, match="429"):
            client.list_folders()


# ---------------------------------------------------------------------------
# UI: the source-scoped Tags panel
# ---------------------------------------------------------------------------

CRAFT_DOC = CraftDoc(id="CD1", title="TPS Cabinet", clickable_link="craftdocs://x")


class FakeCraft:
    def __init__(self, api_url: str, api_key_ref: str) -> None:
        pass

    def list_folders(self) -> list[CraftFolder]:
        return [CraftFolder(id="F1", name="work", document_count=1)]

    def list_documents(self, folder_id: str) -> list[CraftDoc]:
        return [CraftDoc(id="CD0", title="Folder Doc")]

    def fetch_document_markdown(self, doc_id: str) -> str:
        return "body"

    def search_tags(self) -> list[tuple[str, int]]:
        return [("meetings", 9), ("arete", 3)]

    def search_documents_by_tag(self, tag: str) -> list[CraftDoc]:
        return [CRAFT_DOC] if tag == "meetings" else []

    def prepend_markdown(self, doc_id: str, markdown: str) -> None:
        pass

    def clear_cache(self) -> None:
        pass


async def wait_until(pilot, predicate, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        await pilot.pause(0.05)
    raise AssertionError("condition not met before timeout")


def tags_header(app) -> str:
    return str(
        app.query_one(TagList).query_one("#all-tags-header").render()
    )


def tag_names(app) -> list[str]:
    from librarian.widgets.tag_list import TagItem

    lv = app.query_one(TagList).all_tags_list_view
    return [item.tag_name for item in lv.children if isinstance(item, TagItem)]


@pytest.fixture
def vault(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    (root / "local-note.md").write_text("# local #localtag\n")
    (root / "sub").mkdir()
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
    with batch_writes():
        add_file(config.scan_directory / "local-note.md", 1.0, ["localtag"])
    return LibrarianApp(config)


async def enter_craft(app, pilot) -> None:
    """Focus the Craft tree and move the cursor onto its first folder."""
    file_list = app.query_one(FileList)
    await wait_until(pilot, lambda: file_list._files)  # startup settled
    tree = app.query_one(TagList).craft_tree
    tree.focus()
    # Wait for the real folder, not the transient "loading…" placeholder row.
    await wait_until(
        pilot, lambda: any("work" in str(n.label) for n in tree.root.children)
    )
    await pilot.press("down")
    await wait_until(
        pilot, lambda: app.query_one(TagList).active_source == "craft"
    )


class TestScopedPanel:
    async def test_local_scope_at_startup(self, app):
        async with app.run_test(size=(100, 40)) as pilot:
            await wait_until(pilot, lambda: tag_names(app) == ["localtag"])
            assert "ALL TAGS" in tags_header(app)
            assert app.query_one(TagList).tags_scope == "local"

    async def test_entering_craft_flips_the_scope(self, app):
        async with app.run_test(size=(100, 40)) as pilot:
            await enter_craft(app, pilot)
            assert "CRAFT TAGS" in tags_header(app)
            await wait_until(
                pilot, lambda: tag_names(app) == ["meetings", "arete"]
            )

    async def test_returning_to_folders_restores_local_tags(self, app):
        async with app.run_test(size=(100, 40)) as pilot:
            await enter_craft(app, pilot)
            await wait_until(pilot, lambda: tag_names(app) == ["meetings", "arete"])

            tree = app.query_one(TagList).directory_tree
            tree.focus()
            await pilot.press("down")
            await wait_until(pilot, lambda: tag_names(app) == ["localtag"])
            assert "ALL TAGS" in tags_header(app)

    async def test_selecting_a_craft_tag_lists_its_docs(self, app):
        async with app.run_test(size=(100, 40)) as pilot:
            await enter_craft(app, pilot)
            await wait_until(pilot, lambda: tag_names(app) == ["meetings", "arete"])

            tag_list = app.query_one(TagList)
            lv = tag_list.all_tags_list_view
            lv.focus()
            await pilot.pause()
            await pilot.press("enter")

            file_list = app.query_one(FileList)
            await wait_until(
                pilot, lambda: file_list.get_selected_craft_doc() == CRAFT_DOC
            )
            assert tag_list.active_source == "craft-tags"
            assert file_list.get_header_text() == "FILES (craft: #meetings)"

    async def test_selecting_a_local_tag_still_works(self, app):
        async with app.run_test(size=(100, 40)) as pilot:
            await wait_until(pilot, lambda: tag_names(app) == ["localtag"])
            tag_list = app.query_one(TagList)
            lv = tag_list.all_tags_list_view
            lv.focus()
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()

            assert tag_list.active_source == "tags"
            file_list = app.query_one(FileList)
            await wait_until(
                pilot,
                lambda: [p.name for p in file_list._files] == ["local-note.md"],
            )

    async def test_index_update_keeps_the_craft_tag_listing(self, app):
        async with app.run_test(size=(100, 40)) as pilot:
            await enter_craft(app, pilot)
            await wait_until(pilot, lambda: tag_names(app) == ["meetings", "arete"])
            app.query_one(TagList).all_tags_list_view.focus()
            await pilot.pause()
            await pilot.press("enter")
            file_list = app.query_one(FileList)
            await wait_until(
                pilot, lambda: file_list.get_selected_craft_doc() == CRAFT_DOC
            )

            app._refresh_file_panel()
            await pilot.pause(0.3)
            assert file_list.get_selected_craft_doc() == CRAFT_DOC

    async def test_index_refresh_while_craft_scoped_stays_stored(self, app):
        """A background rescan must not paint local tags into a Craft-scoped
        panel; the new local tags appear when the scope flips back."""
        async with app.run_test(size=(100, 40)) as pilot:
            await enter_craft(app, pilot)
            await wait_until(pilot, lambda: tag_names(app) == ["meetings", "arete"])

            app.query_one(TagList).update_tags([("localtag", 1), ("new", 2)])
            await pilot.pause()
            assert tag_names(app) == ["meetings", "arete"]

            tree = app.query_one(TagList).directory_tree
            tree.focus()
            await pilot.press("down")
            await wait_until(
                pilot, lambda: sorted(tag_names(app)) == ["localtag", "new"]
            )
