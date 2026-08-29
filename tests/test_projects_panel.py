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
from pathlib import Path

import pytest

from librarian.config import CalendarConfig, Config, TagConfig, ToolsConfig
from librarian.widgets import TagList

pytest.importorskip("projection", reason="projection is an optional dependency")

# Importable is not the same as new enough. projection's model was reshaped when
# its local store became the source of record, and an older checkout has no
# `ProjectFields` -- so a bare import here raises ImportError during *collection*,
# which aborts the entire run rather than skipping this module. projection is
# installed by hand (it is not in the lockfile, and `uv sync` removes it), so a
# stale one on some machine is an ordinary situation, not a broken install.
if not hasattr(pytest.importorskip("projection.models"), "ProjectFields"):
    pytest.skip(
        "projection predates the local-first model (no ProjectFields) — "
        "reinstall it with `uv pip install -e /path/to/projection`",
        allow_module_level=True,
    )

from projection import panel as panel_module  # noqa: E402
from projection.models import Project, ProjectFields  # noqa: E402
from projection.panel import ProjectsPanel  # noqa: E402
from projection.sync import SyncEvent  # noqa: E402

from librarian.widgets.projects_modal import ProjectsModal, is_available  # noqa: E402


class FakeClient:
    """Smartsheet client that never authenticates or hits the network."""

    async def ensure_ready(self):
        return None

    async def aclose(self):
        return None


def _project(title, remote_id=None, **fields):
    """A project as projection's store holds it: local id, backend key mapped."""
    project = Project(fields=ProjectFields(title=title, **fields))
    if remote_id is not None:
        project.link_remote("smartsheet", remote_id)
    return project


class FakeSync:
    """Stand-in SyncCoordinator serving canned projects.

    Mirrors the fake in projection's own suite; kept local so a change there
    cannot silently alter what these tests exercise.
    """

    def __init__(self, *args, on_event=None, **kwargs):
        self._on_event = on_event
        self._projects = [
            _project("ZTNA", 1, status="In progress"),
            _project("AI Assistant", 2, status="In progress", starred=True),
            _project("Old Migration", 3, status="Done"),
        ]

    async def initial_sync(self):
        return list(self._projects)

    async def refresh(self):
        await asyncio.sleep(0)
        return list(self._projects)

    def load(self):
        return list(self._projects)

    # The panel asks whether there is anything to sync with at all.
    has_backend = True
    backend_name = "smartsheet"

    def conflicted(self):
        return [p for p in self._projects if p.has_conflicts]

    async def resolve_conflict(self, key, field_name, *, take_theirs):
        return False

    def start_polling(self):
        pass

    def stop_polling(self):
        pass

    def last_sync(self):
        return None

    @property
    def last_error(self):
        return None

    def assignee_options(self):
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

    async def toggle_starred(self, key, starred):
        return await self.update_item(key, starred=starred)


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
            assert app.query_one("#tool-tabs").is_mounted
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


@pytest.mark.skipif(
    not hasattr(ProjectsPanel, "action_setup"),
    reason="this projection predates the setup wizard",
)
class TestBackendSetupWhileEmbedded:
    """projection's setup wizard has to work from inside Librarian.

    It is the one dialog a *first-time* user meets, and the embed is where
    projection is normally opened — so "configure it from the shell instead" is
    not an answer available here.
    """

    async def test_comma_opens_setup_over_librarian(self, app, fake_backend):
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await open_panel(app, pilot)

            await pilot.press("comma")
            for _ in range(15):
                await pilot.pause()
                if type(app.screen).__name__ == "SetupModal":
                    break

            modal = app.screen
            assert type(modal).__name__ == "SetupModal"
            # Its own contract, on Librarian's screen stack.
            assert [b.id for b in modal.query("Button")] == [
                "btn-test",
                "btn-cancel",
                "btn-save",
            ]
            assert modal.query("Footer")
            # And Librarian's own single-letter keys stay out of reach.
            assert "s" not in modal.active_bindings
            assert "u" not in modal.active_bindings

    async def test_escape_returns_to_the_panel(self, app, fake_backend):
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await open_panel(app, pilot)

            await pilot.press("comma")
            for _ in range(15):
                await pilot.pause()
                if type(app.screen).__name__ == "SetupModal":
                    break

            await pilot.press("escape")
            for _ in range(10):
                await pilot.pause()

            assert isinstance(app.screen, ProjectsModal)
            assert app.is_running


class TestTheHostDoesNotBuildTheClient:
    """The embed must not construct projection's Smartsheet client.

    Every other test in this file passes a stub client, which is exactly the
    thing that was wrong: Librarian built a bare `SmartsheetClient()`, and since
    projection uses a client it is handed as-is, the panel could not find the
    credential `token_ref` names — "No Smartsheet API token configured" in the
    embed while the standalone app worked. A stub hides that completely, so these
    two tests deliberately do not use one.
    """

    async def test_the_action_hands_over_no_client(self, app, fake_backend, tmp_path):
        """What `t`/Projects actually does, with nothing stubbed in between."""
        from projection.panel import ProjectsPanel as RealPanel

        # projection's sandboxed config (see conftest) names a reference, as a
        # real install does.
        config_file = tmp_path / "pconfig" / "config.toml"
        config_file.write_text(
            'backend = "smartsheet"\n[backends.smartsheet]\n'
            'sheet_id = 1\ntoken_ref = "op://Sandbox/sheets/token"\n'
        )

        async with app.run_test(size=(120, 38)) as pilot:
            await pilot.pause()
            app.action_launch_projects()
            for _ in range(20):
                await pilot.pause()
                panels = app.screen.query("#projects-panel")
                if panels:
                    break

            panel = app.screen.query_one("#projects-panel", RealPanel)
            # It built its own, from projection's config — not one of ours.
            assert panel._owns_client is True
            assert panel._client._credential.secret_ref == "op://Sandbox/sheets/token"

    def test_the_modal_is_opened_without_a_client(self):
        """Belt and braces: the call site itself, read as source.

        A future edit that "helpfully" passes a client would pass every other
        test in this file.
        """
        from pathlib import Path

        import librarian.actions.projects_actions as actions

        source = Path(actions.__file__).read_text()
        assert "ProjectsModal()" in source, "the host must hand over no client"
        assert "ProjectsModal(SmartsheetClient" not in source


class TestRealUserDataIsNeverTouched:
    """The embed must not read or rewrite projection's real store.

    That store is projection's *source of record*, and mounting a panel is enough
    to make it migrate: the panel reads projection's config when it is not handed
    one, and the store path comes from that config. Until `isolate_projection_paths`
    in conftest, nothing stopped this except `fake_backend` happening to stub the
    coordinator out.
    """

    def test_the_store_path_is_redirected(self, tmp_path):
        from projection.config import Config

        assert str(tmp_path) in str(Config.load().data_dir)

    async def test_mounting_a_panel_without_a_fake_backend_stays_in_the_sandbox(
        self, app, tmp_path
    ):
        """Deliberately no `fake_backend`: this is the unguarded path."""
        from projection.local_storage import LocalStorage

        real = Path.home() / ".local" / "share" / "projection"
        before = (real / "projects.json").read_bytes() if (real / "projects.json").exists() else None

        async with app.run_test(size=(120, 38)) as pilot:
            await pilot.pause()
            app.push_screen(ProjectsModal(FakeClient()))
            for _ in range(10):
                await pilot.pause()

        after = (real / "projects.json").read_bytes() if (real / "projects.json").exists() else None
        assert before == after, "the embed rewrote the real projection store"
        # And whatever it did touch went to the sandbox.
        assert str(tmp_path) in str(LocalStorage("projects").path)
