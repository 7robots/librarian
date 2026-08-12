"""Tests for the embedded projects panel.

Skipped when projection is not installed. Unlike remtui, projection lives in a
private repository and is not declared as an optional dependency, so on most
machines -- including CI -- this whole module skips and `test_projects.py`
covers the handoff path instead.

Nothing here reaches Smartsheet or 1Password: the client is a stub and the sync
coordinator is replaced with projection's own fake, the same one its suite uses.
"""

from __future__ import annotations

import asyncio

import pytest

from librarian.config import CalendarConfig, Config, TagConfig, ToolsConfig
from librarian.widgets import TagList

pytest.importorskip("projection", reason="projection is an optional dependency")

from projection import panel as panel_module  # noqa: E402
from projection.models import Project, ProjectProperties  # noqa: E402
from projection.panel import ProjectsPanel  # noqa: E402
from projection.sync import SyncEvent  # noqa: E402

from librarian.widgets.projects_modal import ProjectsModal, is_available  # noqa: E402


class FakeClient:
    """Smartsheet client that never authenticates or hits the network."""

    async def ensure_ready(self):
        return None

    async def aclose(self):
        return None


class FakeSync:
    """Stand-in SyncCoordinator serving canned projects.

    Mirrors the fake in projection's own suite; kept local so a change there
    cannot silently alter what these tests exercise.
    """

    def __init__(self, *args, on_event=None, **kwargs):
        self._on_event = on_event
        self._projects = [
            Project(
                row_id=1,
                title="ZTNA",
                properties=ProjectProperties(status="In progress"),
            ),
            Project(
                row_id=2,
                title="AI Assistant",
                properties=ProjectProperties(status="In progress", sync="Yes"),
            ),
            Project(
                row_id=3,
                title="Old Migration",
                properties=ProjectProperties(status="Done"),
            ),
        ]

    async def initial_sync(self):
        return list(self._projects)

    async def refresh(self):
        await asyncio.sleep(0)
        return list(self._projects)

    def load(self):
        return list(self._projects)

    def start_polling(self):
        pass

    def stop_polling(self):
        pass

    def last_sync(self):
        return None

    @property
    def last_error(self):
        return None

    def contact_options(self):
        return ["Al Pacheco", "Jefferson B"]

    def _emit_data_updated(self):
        if self._on_event:
            self._on_event(SyncEvent(event_type="data_updated"))

    async def update_item(self, key, **kwargs):
        return True

    async def delete_item(self, key):
        self._projects = [p for p in self._projects if p.key != key]
        self._emit_data_updated()
        return True

    async def toggle_sync(self, key, value):
        return await self.update_item(key, sync=value)


@pytest.fixture
def fake_backend(monkeypatch):
    """Swap projection's sync coordinator for the canned one."""
    monkeypatch.setattr(panel_module, "SyncCoordinator", FakeSync)


@pytest.fixture
def config(tmp_path):
    root = tmp_path / "notes"
    root.mkdir()
    return Config(
        scan_directory=root,
        editor="vim",
        tags=TagConfig(),
        export_directory=tmp_path / "exports",
        data_directory=tmp_path / "data",
        calendar=CalendarConfig(),
        tools=ToolsConfig(projects=True),
    )


@pytest.fixture
def app(config, tmp_index):
    from librarian.app import LibrarianApp

    return LibrarianApp(config)


async def open_panel(app, pilot) -> ProjectsPanel:
    """Push the modal with the fake backend and wait for it to load."""
    app.push_screen(ProjectsModal(FakeClient()))
    for _ in range(20):
        await pilot.pause()
        panels = app.screen.query("#projects-panel")
        if panels and panels.first()._projects:
            return panels.first()
    return app.screen.query_one("#projects-panel", ProjectsPanel)


class TestAvailability:
    def test_reports_available_when_installed(self):
        assert is_available() is True


class TestEmbedding:
    async def test_panel_mounts_and_loads(self, app, fake_backend):
        async with app.run_test(size=(120, 38)) as pilot:
            await pilot.pause()
            panel = await open_panel(app, pilot)

            assert isinstance(panel, ProjectsPanel)
            assert [p.title for p in panel._projects] == [
                "ZTNA",
                "AI Assistant",
                "Old Migration",
            ]

    async def test_librarian_stays_visible_behind(self, app, fake_backend):
        """The point of a panel rather than a handoff."""
        async with app.run_test(size=(120, 38)) as pilot:
            await pilot.pause()
            await open_panel(app, pilot)

            tag_list = app.query_one(TagList)
            assert tag_list.directory_tree.is_mounted
            assert tag_list.tools_list_view.is_mounted
            assert app.query_one("#banner-art").is_mounted

    async def test_panel_covers_only_the_right_hand_side(self, app, fake_backend):
        async with app.run_test(size=(120, 38)) as pilot:
            await pilot.pause()
            panel = await open_panel(app, pilot)
            frame = app.screen.query_one("#projects-frame")

            # 75% of 120 columns, leaving the sidebar visible.
            assert frame.size.width == pytest.approx(90, abs=2)
            # Banner and footer rows stay clear.
            assert frame.size.height < app.screen.size.height
            assert panel.size.width < app.screen.size.width

    async def test_hosting_does_not_restyle_librarian(self, app, fake_backend):
        """projection's DEFAULT_CSS is scoped, so it must not leak outward."""
        async with app.run_test(size=(120, 38)) as pilot:
            await pilot.pause()
            tag_list = app.query_one(TagList)
            before = tag_list.directory_tree.styles.border_top

            await open_panel(app, pilot)

            assert tag_list.directory_tree.styles.border_top == before


class TestChrome:
    async def test_the_embed_drops_projections_wordmark(self, app, fake_backend):
        """Librarian's own frame already says PROJECTS above it, and the
        sidebar rows are better spent on the lists."""
        async with app.run_test(size=(120, 38)) as pilot:
            await pilot.pause()
            panel = await open_panel(app, pilot)

            assert not panel.query("#logo")
            assert panel.query_one("#nav")

    async def test_the_frame_still_labels_the_panel(self, app, fake_backend):
        async with app.run_test(size=(120, 38)) as pilot:
            await pilot.pause()
            await open_panel(app, pilot)

            hint = app.screen.query_one("#projects-hint")
            assert "PROJECTS" in str(hint.render())


class TestClosing:
    async def test_q_closes_the_panel_and_librarian_survives(self, app, fake_backend):
        """projection's panel binds `q -> app.quit`, which is Librarian's quit.

        The modal's `priority=True` binding is what stops that; without it the
        panel holds focus and `q` closes Librarian outright.
        """
        async with app.run_test(size=(120, 38)) as pilot:
            await pilot.pause()
            await open_panel(app, pilot)
            assert isinstance(app.screen, ProjectsModal)

            await pilot.press("q")
            await pilot.pause()

            assert not isinstance(app.screen, ProjectsModal)
            assert app.is_running

    async def test_closing_restores_the_folder_view(self, app, fake_backend):
        async with app.run_test(size=(120, 38)) as pilot:
            await pilot.pause()
            tag_list = app.query_one(TagList)
            before = tag_list.active_source

            await open_panel(app, pilot)
            await pilot.press("q")
            await pilot.pause()

            assert tag_list.active_source == before == "folders"
            assert tag_list.directory_tree.display


class TestKeyIsolation:
    """Librarian's own keys must not act while the panel is open."""

    async def test_librarian_search_key_is_inert(self, app, fake_backend):
        from librarian.widgets import FileList

        async with app.run_test(size=(120, 38)) as pilot:
            await pilot.pause()
            await open_panel(app, pilot)

            await pilot.press("s")
            await pilot.pause()

            assert not app.query_one(FileList).is_search_mode()
            assert isinstance(app.screen, ProjectsModal)

    async def test_e_reaches_the_panel_not_librarian(self, app, fake_backend):
        """`e` is edit-file in Librarian and edit-project in projection."""
        async with app.run_test(size=(120, 38)) as pilot:
            await pilot.pause()
            panel = await open_panel(app, pilot)
            panel.focus()
            await pilot.pause()

            await pilot.press("e")
            for _ in range(10):
                await pilot.pause()
                if type(app.screen).__name__ == "EditModal":
                    break

            assert type(app.screen).__name__ == "EditModal"

    async def test_x_does_not_export_a_note(self, app, fake_backend):
        """`x` is export in Librarian and sync-summary in projection."""
        async with app.run_test(size=(120, 38)) as pilot:
            await pilot.pause()
            await open_panel(app, pilot)

            await pilot.press("x")
            for _ in range(5):
                await pilot.pause()

            assert list(app.config.export_directory.glob("*.html")) == []


class TestOlderProjectionCompatibility:
    """The flag is newer than the embed; an older build must still open.

    compose() imports the panel from whatever is installed, so passing an
    unknown keyword raises inside compose -- which fails the whole modal, not
    just the logo.
    """

    async def test_a_panel_without_show_logo_still_mounts(
        self, app, fake_backend, monkeypatch
    ):
        import projection.panel as projection_panel

        class OldPanel(ProjectsPanel):
            """Signature has no `show_logo`, like the build before the flag."""

            def __init__(self, client=None, **kwargs):
                if "show_logo" in kwargs:
                    raise TypeError(
                        "__init__() got an unexpected keyword argument 'show_logo'"
                    )
                super().__init__(client, **kwargs)

        monkeypatch.setattr(projection_panel, "ProjectsPanel", OldPanel)

        async with app.run_test(size=(120, 38)) as pilot:
            await pilot.pause()
            app.push_screen(ProjectsModal(FakeClient()))
            for _ in range(20):
                await pilot.pause()
                if isinstance(app.screen, ProjectsModal):
                    break

            assert isinstance(app.screen, ProjectsModal)
            assert app.is_running
            # It keeps its wordmark -- cosmetic, and better than not opening.
            panel = app.screen.query_one("#projects-panel")
            assert panel.query("#logo")


class TestDialogsWhileEmbedded:
    """The dialog contract has to hold inside Librarian too.

    A dialog opened from an embedded panel is pushed onto *Librarian's* screen
    stack, so the risk is its footer or its keys resolving against the host.
    """

    async def test_edit_dialog_opens_over_librarian_with_its_own_contract(
        self, app, fake_backend
    ):
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            panel = await open_panel(app, pilot)
            panel.query_one("#projects").focus()
            await pilot.pause()

            await pilot.press("e")
            for _ in range(15):
                await pilot.pause()
                if type(app.screen).__name__ == "EditModal":
                    break

            modal = app.screen
            assert type(modal).__name__ == "EditModal"

            buttons = [(b.id, str(b.label)) for b in modal.query("Button")]
            assert buttons == [
                ("btn-editor", "Editor"),
                ("btn-done", "Done"),
                ("btn-cancel", "Cancel"),
                ("btn-save", "Save"),
            ]
            assert modal.query("Footer")
            assert app.focused.id == "title-input"

    async def test_the_dialogs_keys_win_over_librarians(self, app, fake_backend):
        """Librarian binds `e`, `d`, `x`, `n` on the App and `q` on the modal.

        The dialog's own bindings must be what resolves -- and Librarian's must
        not fire underneath.
        """
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            panel = await open_panel(app, pilot)
            panel.query_one("#projects").focus()
            await pilot.pause()

            await pilot.press("e")
            for _ in range(15):
                await pilot.pause()
                if type(app.screen).__name__ == "EditModal":
                    break

            modal = app.screen
            for key, description in (
                ("ctrl+s", "Save"),
                ("ctrl+e", "Editor"),
                ("ctrl+d", "Done"),
                ("escape", "Cancel"),
            ):
                binding = modal.active_bindings.get(key)
                assert binding is not None, f"{key} unreachable inside Librarian"
                assert binding.node is modal, f"{key} resolved to {binding.node!r}"
                assert binding.binding.description == description

            # Librarian's own single-letter actions are not reachable here.
            assert "s" not in modal.active_bindings
            assert "u" not in modal.active_bindings

    async def test_escape_closes_the_dialog_not_the_panel(self, app, fake_backend):
        """Escape should back out one level, leaving the panel up."""
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            panel = await open_panel(app, pilot)
            panel.query_one("#projects").focus()
            await pilot.pause()

            await pilot.press("e")
            for _ in range(15):
                await pilot.pause()
                if type(app.screen).__name__ == "EditModal":
                    break

            await pilot.press("escape")
            for _ in range(10):
                await pilot.pause()

            assert isinstance(app.screen, ProjectsModal)
            assert app.is_running
