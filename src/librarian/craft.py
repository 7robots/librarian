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
from concurrent.futures import ThreadPoolExecutor
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

# The RE2 pattern sent to /documents/search for tag discovery: the scanner's
# tag rules, with the same whitespace-or-start requirement that keeps URL
# fragments from reading as tags.
TAG_SEARCH_REGEXP = r"(^|\s)#[a-zA-Z][a-zA-Z0-9_-]*"

# Client-side extraction from matched blocks' raw markdown -- the same rule as
# scanner.TAG_PATTERN, so the local and Craft tag panels agree on what a tag is.
TAG_EXTRACT_PATTERN = re.compile(r"(?<![^\s])#([a-zA-Z][a-zA-Z0-9_-]*)")


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
        # One retry on a server-side error or throttle: a burst of quick GETs
        # (folder walks, title lookups) can catch a transient 502 or a 429,
        # and a single one must not fail the lot.
        for attempt in (1, 2):
            try:
                with urllib.request.urlopen(
                    request, timeout=REQUEST_TIMEOUT_SECONDS
                ) as response:
                    return response.read().decode("utf-8")
            except urllib.error.HTTPError as e:
                if (e.code >= 500 or e.code == 429) and attempt == 1:
                    time.sleep(_retry_delay(e))
                    continue
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

    def search_tags(self) -> list[tuple[str, int]]:
        """Every tag in the space with its document count.

        One space-wide regex search; tags are extracted from the result
        snippets, which bold each *matched region* as `**...**` and elide
        unmatched context as `...` -- so the tags themselves are always
        present in full, once the bold markers are stripped. `fetchBlocks`
        is no help here: for most matches it returns the enclosing *page*
        block, whose text is the document title, not the tag line (verified
        live 2026-08-28: 68 of 83 matches). Semantics mirror the scanner:
        case-insensitive dedupe keeping the first-seen casing, sorted by
        count descending then name.
        """
        return self._cached("tags", self._load_tags)

    def _load_tags(self) -> list[tuple[str, int]]:
        query = urllib.parse.urlencode({"regexps": TAG_SEARCH_REGEXP})
        data = self._get_json(f"/documents/search?{query}")

        docs_by_tag: dict[str, set[str]] = {}
        casing: dict[str, str] = {}
        for item in data.get("items") or []:
            doc_id = str(item.get("documentId") or "")
            snippet = str(item.get("markdown") or "").replace("**", "")
            for tag in TAG_EXTRACT_PATTERN.findall(snippet):
                key = tag.lower()
                casing.setdefault(key, tag)
                docs_by_tag.setdefault(key, set()).add(doc_id)

        counts = [(casing[key], len(ids)) for key, ids in docs_by_tag.items()]
        counts.sort(key=lambda item: (-item[1], item[0].lower()))
        return counts

    def search_documents_by_tag(self, tag: str) -> list[CraftDoc]:
        """The documents carrying a tag, newest-modified first.

        Search results carry neither title nor clickable link, so titles are
        resolved per document and links built from the connection's URL
        template.
        """
        return self._cached(
            f"tagdocs:{tag.lower()}", lambda: self._load_tag_docs(tag)
        )

    def _load_tag_docs(self, tag: str) -> list[CraftDoc]:
        query = urllib.parse.urlencode(
            {"regexps": rf"(^|\s)#{re.escape(tag)}\b"}
        )
        data = self._get_json(f"/documents/search?{query}")

        entries: list[tuple[str, str]] = []  # (doc_id, lastModifiedAt)
        seen: set[str] = set()
        for item in data.get("items") or []:
            doc_id = str(item.get("documentId") or "")
            if not doc_id or doc_id in seen:
                continue
            seen.add(doc_id)
            entries.append((doc_id, str(item.get("lastModifiedAt") or "")))

        # Search results carry neither title nor link. Docs already known
        # from cached folder listings (browsing warms these) come free; the
        # rest resolve one title GET each on a *small* pool -- 6 workers
        # tripped the API's rate limit at 66 docs, and a full folder walk was
        # worse (116 folders, ~75s). One unresolvable title must not fail the
        # listing.
        known = self._docs_from_cached_listings()

        def resolve(entry: tuple[str, str]) -> CraftDoc:
            doc_id, modified = entry
            hit = known.get(doc_id)
            if hit is not None:
                return hit
            try:
                title = self.fetch_document_title(doc_id)
            except CraftError:
                title = "(untitled)"
            return CraftDoc(
                id=doc_id,
                title=title,
                clickable_link=self.app_url_for(doc_id),
                last_modified=modified,
            )

        # Prime the URL template once, outside the pool.
        self.app_url_for("")
        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(resolve, entries))

    def _docs_from_cached_listings(self) -> dict[str, CraftDoc]:
        """Docs known from folder listings already in the cache. No network."""
        now = time.monotonic()
        known: dict[str, CraftDoc] = {}
        for key, (stamp, value) in list(self._cache.items()):
            if key.startswith("docs:") and now - stamp < CACHE_TTL_SECONDS:
                for doc in value:
                    known[doc.id] = doc
        return known

    def fetch_document_title(self, doc_id: str) -> str:
        """A document's title: the root page block's markdown."""
        return self._cached(f"title:{doc_id}", lambda: self._load_title(doc_id))

    def _load_title(self, doc_id: str) -> str:
        query = urllib.parse.urlencode({"id": doc_id, "maxDepth": "0"})
        data = self._get_json(f"/blocks?{query}")
        return str(data.get("markdown") or "") or "(untitled)"

    def app_url_for(self, block_id: str) -> str:
        """A craftdocs:// link for a block id, from the connection's template.

        Listings' own `clickableLink` uses a different `documentId`; search
        results carry no link at all, so this template (which takes the root
        *block* id -- the API's document id) is what a tag listing gets.
        """
        template = self._cached("app-url-template", self._load_url_template)
        if not template or "{blockId}" not in template:
            return ""
        return template.replace("{blockId}", block_id)

    def _load_url_template(self) -> str:
        data = self._get_json("/connection")
        templates = data.get("urlTemplates") or {}
        return str(templates.get("app") or "")

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


def _retry_delay(error: urllib.error.HTTPError) -> float:
    """Seconds to wait before the one retry, honoring Retry-After if sane."""
    retry_after = error.headers.get("Retry-After") if error.headers else None
    try:
        return min(max(float(retry_after), 0.5), 10.0)
    except (TypeError, ValueError):
        return 1.0


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
