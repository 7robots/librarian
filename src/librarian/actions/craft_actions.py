"""Craft module actions for LibrarianApp.

The Craft panel is a sidebar tree of remote folders; the Files panel lists the
highlighted folder's documents and the preview shows a document's markdown.
Every fetch runs in a worker with `exit_on_error=False` -- a broken connection
is reported where it happened, never taken as the app going down, and never
displayed as an empty space.
"""

from __future__ import annotations

import subprocess

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
        """Build the client and start loading folders. Called once at mount."""
        self._craft = CraftClient(
            self.config.craft.api_url, self.config.craft.api_key_ref
        )
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
        """Start the markdown fetch once the cursor has settled on a doc."""
        self._preview_timer = None
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

    def _open_in_craft(self, doc: CraftDoc) -> None:
        """Open a document in Craft.app via its clickable link.

        The link is used verbatim -- its `documentId` is not the API `id`, so
        it cannot be rebuilt locally.
        """
        if not doc.clickable_link:
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
