"""Craft REST API client: folders, documents, and document markdown.

Talks to a Craft space-level API connection (connect.craft.do). Two settings
drive it: the connection URL (`[craft] api_url`) and a 1Password reference to
the API key (`[craft] api_key_ref`). The key itself is never stored -- it is
resolved lazily via `op read`, on the first request, so startup never blocks on
1Password and the value never touches config or disk.

Failures raise `CraftError` rather than returning empty listings, so a broken
connection is never displayed as an empty space -- the same contract as
`calendar.py`.
"""

import json
import re
import subprocess
import textwrap
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

# Craft's built-in locations come back from /folders alongside real folders.
# v1 browses the user's own folder tree only.
SYSTEM_FOLDER_IDS = frozenset({"unsorted", "daily_notes", "trash", "templates"})

# Listings change rarely mid-session; previews are cached per doc. Same TTL as
# the calendar cache.
CACHE_TTL_SECONDS = 300

REQUEST_TIMEOUT_SECONDS = 15

# Craft's edge blocks urllib's default agent outright (403 for
# "Python-urllib/*", 200 for anything else -- verified against the live API),
# so every request identifies as librarian.
USER_AGENT = "librarian"

# A line consisting only of hashtags (e.g. "#meetings" or "#meetings #q3"),
# using the same tag syntax the scanner indexes. Meeting notes keep such a
# line directly beneath the title; a prepended occurrence goes below it.
TAG_LINE_PATTERN = re.compile(
    r"#[a-zA-Z][a-zA-Z0-9_-]*(?:\s+#[a-zA-Z][a-zA-Z0-9_-]*)*"
)


def is_tag_line(text: str) -> bool:
    """Whether a block's markdown is a tag-only line."""
    return bool(TAG_LINE_PATTERN.fullmatch(text.strip()))


class CraftError(Exception):
    """Raised when the Craft API cannot be reached or answers with an error."""


@dataclass
class CraftFolder:
    """A folder in the Craft space, with its subfolders."""

    id: str
    name: str
    document_count: int
    folders: list["CraftFolder"] = field(default_factory=list)


@dataclass
class CraftDoc:
    """A document listing entry. `clickable_link` opens it in Craft.app.

    The link is used verbatim, never rebuilt from `id`: the API's `id` and the
    link's `documentId` are *different* identifiers for the same doc.
    """

    id: str
    title: str
    clickable_link: str = ""
    last_modified: str = ""


def resolve_api_key(reference: str) -> str:
    """Resolve a 1Password reference (op://...) to the API key via `op read`.

    The value is returned to the caller and nowhere else -- never logged,
    never written.
    """
    if not reference:
        raise CraftError(
            "No Craft API key reference configured. "
            "Set api_key_ref under [craft] to an op:// reference."
        )
    try:
        result = subprocess.run(
            ["op", "read", reference],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except FileNotFoundError:
        raise CraftError("1Password CLI (op) not found on PATH") from None
    except subprocess.TimeoutExpired:
        raise CraftError("op read timed out resolving the Craft API key") from None

    if result.returncode != 0:
        stderr = (result.stderr or "").strip().splitlines()
        detail = stderr[0] if stderr else f"exit {result.returncode}"
        if "authorization timeout" in detail.lower():
            raise CraftError(
                "1Password is locked -- unlock the 1Password app and retry"
            )
        raise CraftError(f"op read failed: {detail}")

    key = result.stdout.strip()
    if not key:
        raise CraftError(f"op read returned nothing for {reference}")
    return key


def unwrap_page_markdown(text: str) -> str:
    """Reduce the API's markdown envelope to plain markdown.

    `GET /blocks` with `Accept: text/markdown` wraps the document:

        <page id="...">
          <pageTitle>Title</pageTitle>
          <content>
              ...markdown, indented...
          </content>
        </page>

    The content is extracted and dedented; any remaining Craft tokens
    (`<callout>`, `<highlight>`, `<caption>`, nested `<page>`) are stripped,
    keeping their inner text, since the Textual Markdown widget would render
    them as literal angle-bracket noise.
    """
    match = re.search(r"<content>\n(.*)\n\s*</content>", text, re.DOTALL)
    if match is not None:
        text = textwrap.dedent(match.group(1))
    # The lookahead keeps the strip to exactly these tag names: without it,
    # unrelated words in angle brackets (<pages>, <contented>) vanish from
    # the preview too.
    return re.sub(
        r"</?(?:page|pageTitle|content|callout|highlight|caption)(?=[\s/>])[^>]*>",
        "",
        text,
    )


class CraftClient:
    """Minimal client for the endpoints Librarian uses, with a TTL cache."""

    def __init__(self, api_url: str, api_key_ref: str) -> None:
        self._api_url = api_url.rstrip("/")
        self._api_key_ref = api_key_ref
        self._api_key: str | None = None
        # Requests run on worker threads; without the lock, two first-use
        # fetches overlapping would run `op read` twice -- two 1Password
        # authorization prompts for one key.
        self._key_lock = threading.Lock()
        self._cache: dict[str, tuple[float, object]] = {}

    # -- transport ---------------------------------------------------------

    def _request(
        self,
        path: str,
        accept: str = "application/json",
        method: str = "GET",
        body: dict | None = None,
    ) -> str:
        """Call `path` and return the response body, or raise CraftError."""
        if not self._api_url:
            raise CraftError(
                "No Craft connection URL configured. "
                "Set api_url under [craft] to the connection's API URL."
            )
        with self._key_lock:
            if self._api_key is None:
                self._api_key = resolve_api_key(self._api_key_ref)

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": accept,
            "User-Agent": USER_AGENT,
        }
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = urllib.request.Request(
            f"{self._api_url}{path}",
            headers=headers,
            data=data,
            method=method,
        )
        try:
            with urllib.request.urlopen(
                request, timeout=REQUEST_TIMEOUT_SECONDS
            ) as response:
                return response.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            raise CraftError(f"Craft API: {_http_error_detail(e)}") from None
        except urllib.error.URLError as e:
            raise CraftError(f"Craft API unreachable: {e.reason}") from None
        except TimeoutError:
            raise CraftError("Craft API timed out") from None

    def _get_json(self, path: str) -> dict:
        body = self._request(path)
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            raise CraftError("Craft API returned unreadable output") from None

    def _cached(self, key: str, load):
        now = time.monotonic()
        hit = self._cache.get(key)
        if hit is not None and now - hit[0] < CACHE_TTL_SECONDS:
            return hit[1]
        value = load()
        self._cache[key] = (now, value)
        return value

    def clear_cache(self) -> None:
        self._cache.clear()

    # -- endpoints ----------------------------------------------------------

    def list_folders(self) -> list[CraftFolder]:
        """The space's folder tree, without Craft's built-in locations."""
        return self._cached("folders", self._load_folders)

    def _load_folders(self) -> list[CraftFolder]:
        data = self._get_json("/folders")
        # `or []` throughout: an explicit JSON null must read as empty, not
        # surface a raw TypeError in a notification (icalPal taught this).
        return [
            _parse_folder(raw)
            for raw in data.get("items") or []
            if raw.get("id") not in SYSTEM_FOLDER_IDS
        ]

    def list_documents(self, folder_id: str) -> list[CraftDoc]:
        """The documents directly in a folder."""
        return self._cached(
            f"docs:{folder_id}", lambda: self._load_documents(folder_id)
        )

    def _load_documents(self, folder_id: str) -> list[CraftDoc]:
        query = urllib.parse.urlencode(
            {"folderId": folder_id, "fetchMetadata": "true"}
        )
        data = self._get_json(f"/documents?{query}")
        return [_parse_doc(raw) for raw in data.get("items") or []]

    def fetch_document_markdown(self, doc_id: str) -> str:
        """A document's body as plain markdown."""
        return self._cached(f"md:{doc_id}", lambda: self._load_markdown(doc_id))

    def _load_markdown(self, doc_id: str) -> str:
        query = urllib.parse.urlencode({"id": doc_id})
        body = self._request(f"/blocks?{query}", accept="text/markdown")
        return unwrap_page_markdown(body)

    def list_child_blocks(self, doc_id: str) -> list[tuple[str, str]]:
        """The document's direct child blocks as (id, markdown) pairs.

        Never cached: this is read immediately before a write, where a stale
        first-block id would anchor the insert on a block that may be gone.
        """
        query = urllib.parse.urlencode({"id": doc_id, "maxDepth": "1"})
        data = self._get_json(f"/blocks?{query}")
        return [
            (str(raw.get("id", "")), str(raw.get("markdown", "")))
            for raw in data.get("content") or []
        ]

    def prepend_markdown(self, doc_id: str, markdown: str) -> None:
        """Insert markdown at the top of a document's body.

        When the first body block is a tag-only line (a `#tag` beneath the
        title, as meeting notes keep), the insert is anchored *after* it;
        otherwise it goes at `position: "start"`. Both placements and the
        preservation of multi-block order were verified against the live API
        (2026-08-28).

        The target is required: the API silently routes an insert with no
        `pageId` into today's daily note, so a missing id must fail loudly
        here rather than write somewhere surprising.
        """
        if not doc_id:
            raise CraftError("prepend needs a document id -- refusing to send")

        # The sibling anchor cannot carry a pageId too (the API 400s on both
        # keys together), but the race is closed server-side: a siblingId that
        # no longer exists 404s rather than falling back to the daily note --
        # verified live 2026-08-28.
        children = self.list_child_blocks(doc_id)
        if children and children[0][0] and is_tag_line(children[0][1]):
            position = {"position": "after", "siblingId": children[0][0]}
        else:
            position = {"position": "start", "pageId": doc_id}

        self._request(
            "/blocks",
            method="POST",
            body={"markdown": markdown, "position": position},
        )
        # The document changed; its cached preview is now stale.
        self._cache.pop(f"md:{doc_id}", None)


def _http_error_detail(error: urllib.error.HTTPError) -> str:
    """The API's own error message when it sent one, else the HTTP status."""
    try:
        payload = json.loads(error.read().decode("utf-8"))
        message = payload["errors"][0]["message"]
        return f"{error.code}: {message}"
    except Exception:
        return f"HTTP {error.code}"


def _parse_folder(raw: dict) -> CraftFolder:
    return CraftFolder(
        id=str(raw.get("id", "")),
        name=str(raw.get("name", "")),
        document_count=int(raw.get("documentCount") or 0),
        folders=[_parse_folder(child) for child in raw.get("folders") or []],
    )


def _parse_doc(raw: dict) -> CraftDoc:
    return CraftDoc(
        id=str(raw.get("id", "")),
        title=str(raw.get("title", "")) or "(untitled)",
        clickable_link=str(raw.get("clickableLink") or ""),
        last_modified=str(raw.get("lastModifiedAt") or ""),
    )
