"""Craft module actions for LibrarianApp.

The Craft panel is a sidebar tree of remote folders; the Files panel lists the
highlighted folder's documents and the preview shows a document's markdown.
Every fetch runs in a worker with `exit_on_error=False` -- a broken connection
is reported where it happened, never taken as the app going down, and never
displayed as an empty space.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from datetime import date
from pathlib import Path

from textual.css.query import NoMatches

from ..craft import CraftClient, CraftDoc, CraftFolder
from ..widgets import FileList, TagList
from ..widgets.craft_tree import CraftTree


class CraftActionsMixin:
    """Mixin providing Craft browsing actions.

    Listed before FileActionsMixin in the app's bases: `action_edit` here
    intercepts `e` when a Craft document is highlighted and defers to the
    file-based edit otherwise.
    """

    def _craft_tree(self) -> CraftTree | None:
        return self.query_one("#tag-list", TagList).craft_tree

    def _init_craft(self) -> None:
        """Build the client. Called once at mount; fetches nothing.

        The folder fetch waits for the panel's first focus (see CraftTree),
        because it resolves the API key via `op read` -- a possible 1Password
        prompt that must not fire at startup.
        """
        self._craft = CraftClient(
            self.config.craft.api_url, self.config.craft.api_key_ref
        )

    def on_craft_tree_load_requested(self, event: CraftTree.LoadRequested) -> None:
        """First focus on the Craft panel: fetch the folder tree."""
        tree = self._craft_tree()
        if tree is not None:
            tree.show_message("loading…")
        self.run_worker(
            self._craft.list_folders,
            name="_fetch_craft_folders",
            thread=True,
            group="craft-folders",
            exclusive=True,
            # A connection that cannot be read is reported in the panel; it
            # must not take the app down, which run_worker does by default.
            exit_on_error=False,
        )

    def _fetch_craft_docs(self, folder: CraftFolder) -> None:
        """List a folder's documents in a background worker."""
        self.run_worker(
            lambda: (folder, self._craft.list_documents(folder.id)),
            name="_fetch_craft_docs",
            thread=True,
            group="craft-docs",
            exclusive=True,
            exit_on_error=False,
        )

    def _refresh_craft_docs(self) -> None:
        """Repopulate the Files panel for the Craft tree's selected folder.

        Cheap when the listing is cached; used after leaving search mode and on
        index updates, where the folder under the cursor has not changed.
        """
        tree = self._craft_tree()
        if tree is None or tree.cursor_node is None:
            return
        folder = tree.cursor_node.data
        if isinstance(folder, CraftFolder):
            self._fetch_craft_docs(folder)

    def on_tag_list_craft_folder_highlighted(
        self, event: TagList.CraftFolderHighlighted
    ) -> None:
        """Show the highlighted Craft folder's documents in the Files panel."""
        self._nav_stack.clear()
        self._fetch_craft_docs(event.folder)

    def on_file_list_craft_doc_highlighted(
        self, event: FileList.CraftDocHighlighted
    ) -> None:
        """Fetch and preview a Craft document, with the usual debounce.

        Staleness is checked before cancelling, exactly as the file handler
        does: a highlight for a doc no longer selected must not kill a preview
        timer the current listing has armed.
        """
        file_list = self.query_one("#file-list", FileList)
        selected = file_list.get_selected_craft_doc()
        if selected is None or selected.id != event.doc.id:
            return

        self._cancel_preview_timers()
        doc = event.doc
        from ..app import PREVIEW_DEBOUNCE

        self._preview_timer = self.set_timer(
            PREVIEW_DEBOUNCE, lambda: self._do_craft_preview(doc)
        )

    def _do_craft_preview(self, doc: CraftDoc) -> None:
        """Start the markdown fetch once the cursor has settled on a doc.

        Cancels rather than assigns: the prepend success handler calls this
        directly, and a plain `= None` there would orphan an armed timer.
        """
        self._cancel_preview_timers()
        # Same worker group as local previews, so whichever the cursor lands on
        # last -- file or Craft doc -- cancels the load it supersedes.
        self.run_worker(
            lambda: (doc, self._craft.fetch_document_markdown(doc.id)),
            name="_load_craft_preview",
            thread=True,
            group="preview",
            exclusive=True,
            exit_on_error=False,
        )

    async def action_edit(self) -> None:
        """`e` on a Craft document opens it in Craft.app; otherwise edit files."""
        file_list = self.query_one("#file-list", FileList)
        doc = file_list.get_selected_craft_doc()
        if doc is not None:
            self._open_in_craft(doc)
            return
        await super().action_edit()

    # -- prepend flow ---------------------------------------------------------
    #
    # `a` on a Craft document: compose a new occurrence in the editor, then
    # insert it at the top of the note (below a leading tag line, when the note
    # has one). Prepend-only, deliberately: whole-document replace would mint
    # new block ids for every block, breaking deeplinks and comments.

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """`a` means add-occurrence only while a Craft document is selected.

        Disabled means Textual keeps looking, so the key falls through to the
        calendar's associate binding the rest of the time -- the same
        mechanism the vim prefix uses.
        """
        if action == "craft_add_occurrence":
            if not self.config.tools.is_enabled("craft"):
                return False
            try:
                file_list = self.query_one("#file-list", FileList)
            except NoMatches:
                return False
            return file_list.get_selected_craft_doc() is not None
        return super().check_action(action, parameters)

    def action_craft_add_occurrence(self) -> None:
        """Compose a new occurrence in the editor and prepend it to the note."""
        file_list = self.query_one("#file-list", FileList)
        doc = file_list.get_selected_craft_doc()
        if doc is None:
            return

        editor = self.config.editor
        editor_path = Path(editor)
        if not (
            editor_path.is_absolute() and editor_path.exists()
        ) and not shutil.which(editor):
            self.notify(f"Editor '{editor}' not found on PATH", severity="error")
            return

        template = f"## {date.today().isoformat()}\n\n"
        fd, tmp_name = tempfile.mkstemp(suffix=".md", prefix="craft-occurrence-")
        tmp = Path(tmp_name)
        try:
            with open(fd, "w", encoding="utf-8") as f:
                f.write(template)

            with self.suspend():
                subprocess.run([editor, str(tmp)], check=False)

            # errors="replace": an editor that saved non-UTF-8 still carries
            # the user's occurrence; mangled characters beat a crash.
            content = tmp.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            self.notify(f"Could not compose occurrence: {e}", severity="error")
            return
        finally:
            tmp.unlink(missing_ok=True)

        # An untouched or emptied buffer means the user changed their mind;
        # nothing is sent.
        if not content.strip() or content.strip() == template.strip():
            self.notify("Nothing added -- occurrence left empty")
            return

        self.run_worker(
            lambda: (doc, self._craft.prepend_markdown(doc.id, content)),
            name="_craft_prepend",
            thread=True,
            group="craft-prepend",
            exclusive=True,
            exit_on_error=False,
        )

    def _open_in_craft(self, doc: CraftDoc) -> None:
        """Open a document in Craft.app via its clickable link.

        The link is used verbatim -- its `documentId` is not the API `id`, so
        it cannot be rebuilt locally.
        """
        # The link comes from the API; only the Craft scheme is ever handed to
        # `open`, so unexpected data cannot launch anything else.
        if not doc.clickable_link.startswith("craftdocs://"):
            self.notify(
                f"No Craft link for '{doc.title}'", severity="warning"
            )
            return
        try:
            subprocess.Popen(
                ["open", doc.clickable_link],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as e:
            self.notify(f"Could not open Craft: {e}", severity="error")
            return
        self.notify(f"Opened in Craft: {doc.title}")
