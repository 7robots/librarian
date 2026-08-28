"""Tests for Craft tag discovery and per-tag document listings (client side)."""

import json
import urllib.error
from io import BytesIO

import pytest

from librarian.craft import (
    CraftClient,
    CraftError,
    _retry_delay,
)

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
