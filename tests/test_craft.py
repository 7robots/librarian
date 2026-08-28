"""Tests for the Craft API client: parsing, errors, caching, key resolution."""

import json
import urllib.error
from io import BytesIO

import pytest

from librarian.craft import (
    CraftClient,
    CraftDoc,
    CraftError,
    CraftFolder,
    _http_error_detail,
    resolve_api_key,
    unwrap_page_markdown,
)

FOLDERS_JSON = json.dumps(
    {
        "items": [
            {"id": "unsorted", "name": "Unsorted", "documentCount": 0, "folders": []},
            {"id": "trash", "name": "Recently Deleted", "documentCount": 3, "folders": []},
            {
                "id": "F1",
                "name": "techne",
                "documentCount": 2,
                "folders": [
                    {"id": "F2", "name": "dev", "documentCount": 1, "folders": []}
                ],
            },
        ]
    }
)

DOCS_JSON = json.dumps(
    {
        "items": [
            {
                "id": "D1",
                "title": "Working with Modal",
                "lastModifiedAt": "2025-11-09T16:47:12.000Z",
                "clickableLink": "craftdocs://open?spaceId=S&documentId=OTHER",
            },
            {"id": "D2", "title": ""},
        ]
    }
)

PAGE_MARKDOWN = (
    '<page id="D1">\n'
    "  <pageTitle>Working with Modal</pageTitle>\n"
    "  <content>\n"
    "    ## Heading\n"
    "    \n"
    "    body <highlight color=\"yellow\">bright</highlight> text\n"
    "  </content>\n"
    "</page>"
)


def client_with(responses: dict[str, str]) -> CraftClient:
    """A client whose transport answers from a canned path->body map."""
    client = CraftClient("https://example.test/api/v1", "op://x/y/z")
    calls = []

    def fake_request(path, accept="application/json"):
        calls.append(path)
        for prefix, body in responses.items():
            if path.startswith(prefix):
                return body
        raise AssertionError(f"unexpected path {path}")

    client._request = fake_request
    client._calls = calls
    return client


class TestUnwrapPageMarkdown:
    def test_extracts_and_dedents_the_content(self):
        text = unwrap_page_markdown(PAGE_MARKDOWN)
        assert "## Heading" in text
        assert not text.startswith(" ")
        assert "<page" not in text
        assert "<content>" not in text

    def test_strips_craft_tokens_but_keeps_their_text(self):
        text = unwrap_page_markdown(PAGE_MARKDOWN)
        assert "bright" in text
        assert "<highlight" not in text
        assert "</highlight>" not in text

    def test_plain_markdown_passes_through(self):
        assert unwrap_page_markdown("# Title\n\nbody") == "# Title\n\nbody"

    def test_unrelated_angle_bracket_words_survive(self):
        """Only Craft's exact tag names are stripped, not words containing them."""
        text = "uses <pages> and <contented> and <caption-foo>"
        assert unwrap_page_markdown(text) == text


class TestListFolders:
    def test_system_folders_are_filtered(self):
        client = client_with({"/folders": FOLDERS_JSON})
        folders = client.list_folders()
        assert [f.name for f in folders] == ["techne"]

    def test_subfolders_are_nested(self):
        client = client_with({"/folders": FOLDERS_JSON})
        techne = client.list_folders()[0]
        assert techne.document_count == 2
        assert [f.name for f in techne.folders] == ["dev"]

    def test_listing_is_cached(self):
        client = client_with({"/folders": FOLDERS_JSON})
        client.list_folders()
        client.list_folders()
        assert client._calls == ["/folders"]

    def test_clear_cache_forces_a_reload(self):
        client = client_with({"/folders": FOLDERS_JSON})
        client.list_folders()
        client.clear_cache()
        client.list_folders()
        assert len(client._calls) == 2

    def test_unreadable_json_raises(self):
        client = client_with({"/folders": "not json"})
        with pytest.raises(CraftError, match="unreadable"):
            client.list_folders()

    def test_explicit_null_items_read_as_empty(self):
        """A JSON null must not surface a raw TypeError (the icalPal lesson)."""
        client = client_with({"/folders": '{"items": null}'})
        assert client.list_folders() == []


class TestListDocuments:
    def test_documents_parse_with_metadata(self):
        client = client_with({"/documents": DOCS_JSON})
        docs = client.list_documents("F1")
        assert docs[0].title == "Working with Modal"
        assert docs[0].clickable_link.startswith("craftdocs://")
        assert "/documents?folderId=F1" in client._calls[0]

    def test_untitled_documents_get_a_placeholder(self):
        client = client_with({"/documents": DOCS_JSON})
        assert client.list_documents("F1")[1].title == "(untitled)"


class TestFetchMarkdown:
    def test_markdown_is_unwrapped(self):
        client = client_with({"/blocks": PAGE_MARKDOWN})
        text = client.fetch_document_markdown("D1")
        assert "## Heading" in text
        assert "<page" not in text


class TestErrors:
    def test_missing_api_url_is_reported(self):
        client = CraftClient("", "op://x/y/z")
        with pytest.raises(CraftError, match="No Craft connection URL"):
            client.list_folders()

    def test_http_error_uses_the_apis_message(self):
        error = urllib.error.HTTPError(
            url="u",
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=BytesIO(
                b'{"errors":[{"code":"NOT_FOUND_ERROR","message":"Folder not found: nope"}]}'
            ),
        )
        assert _http_error_detail(error) == "404: Folder not found: nope"

    def test_http_error_without_a_body_reports_the_status(self):
        error = urllib.error.HTTPError(
            url="u", code=500, msg="boom", hdrs=None, fp=BytesIO(b"")
        )
        assert _http_error_detail(error) == "HTTP 500"


class TestResolveApiKey:
    def test_empty_reference_is_reported(self):
        with pytest.raises(CraftError, match="No Craft API key reference"):
            resolve_api_key("")

    def test_missing_op_binary(self, monkeypatch):
        def raise_missing(*args, **kwargs):
            raise FileNotFoundError("op")

        monkeypatch.setattr("librarian.craft.subprocess.run", raise_missing)
        with pytest.raises(CraftError, match="op.*not found"):
            resolve_api_key("op://x/y/z")

    def test_locked_1password_asks_for_unlock(self, monkeypatch):
        class Result:
            returncode = 1
            stdout = ""
            stderr = "[ERROR] authorization timeout\n"

        monkeypatch.setattr(
            "librarian.craft.subprocess.run", lambda *a, **k: Result()
        )
        with pytest.raises(CraftError, match="unlock the 1Password app"):
            resolve_api_key("op://x/y/z")

    def test_success_returns_the_stripped_value(self, monkeypatch):
        class Result:
            returncode = 0
            stdout = "pdk_secret\n"
            stderr = ""

        monkeypatch.setattr(
            "librarian.craft.subprocess.run", lambda *a, **k: Result()
        )
        assert resolve_api_key("op://x/y/z") == "pdk_secret"
