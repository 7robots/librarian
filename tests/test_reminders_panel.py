"""Tests for the embedded reminders panel.

Skipped when remtui is not installed: it is an optional dependency, and needs
Python 3.12+, so these cannot be a hard requirement.
"""

import sys
from pathlib import Path

import pytest

from librarian.config import CalendarConfig, Config, TagConfig, ToolsConfig
from librarian.widgets import TagList

pytest.importorskip("remtui", reason="remtui is an optional dependency")

from remtui.client import RemctlClient  # noqa: E402
from remtui.panel import RemindersPanel  # noqa: E402

from librarian.widgets.reminders_modal import RemindersModal, is_available  # noqa: E402

# remtui ships a fake remctl for its own tests; reuse it so nothing here reads
# or writes real reminders.


def fake_client(tmp_path, monkeypatch) -> RemctlClient:
    """A client backed by remtui's fake remctl, with state in tmp_path."""
    import remtui

    fake = Path(remtui.__file__).parent / "fake_remctl.py"
    if not fake.exists():
        pytest.skip("remtui's fake remctl backend is not available")
    monkeypatch.setenv("REMTUI_FAKE_STATE", str(tmp_path / "reminders.json"))
    return RemctlClient([sys.executable, str(fake)])


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
        tools=ToolsConfig(reminders=True),
    )


@pytest.fixture
def app(config, tmp_index):
    from librarian.app import LibrarianApp

    return LibrarianApp(config)


async def open_panel(app, pilot, tmp_path, monkeypatch):
    """Push the modal with the fake backend and wait for it to load."""
    app.push_screen(RemindersModal(fake_client(tmp_path, monkeypatch)))
    for _ in range(20):
        await pilot.pause()
        panels = app.screen.query("#reminders-panel")
        if panels and panels.first().reminders:
            return panels.first()
    return app.screen.query_one("#reminders-panel", RemindersPanel)


class TestAvailability:
    def test_reports_available_when_installed(self):
        assert is_available() is True


class TestEmbedding:
    async def test_panel_mounts_and_loads(self, app, tmp_path, monkeypatch):
        async with app.run_test(size=(120, 38)) as pilot:
            await pilot.pause()
            panel = await open_panel(app, pilot, tmp_path, monkeypatch)

            assert isinstance(panel, RemindersPanel)
            assert panel.reminders  # the fake backend has today's reminders
            assert panel.lists

    async def test_librarian_stays_visible_behind(self, app, tmp_path, monkeypatch):
        """The point of a panel rather than a handoff."""
        async with app.run_test(size=(120, 38)) as pilot:
            await pilot.pause()
            await open_panel(app, pilot, tmp_path, monkeypatch)

            # The folder tree and Tools menu belong to the screen underneath and
            # are still mounted.
            tag_list = app.query_one(TagList)
            assert tag_list.directory_tree.is_mounted
            assert app.query_one("#banner-art").is_mounted

    async def test_panel_covers_only_the_right_hand_side(self, app, tmp_path, monkeypatch):
        async with app.run_test(size=(120, 38)) as pilot:
            await pilot.pause()
            panel = await open_panel(app, pilot, tmp_path, monkeypatch)
            frame = app.screen.query_one("#reminders-frame")

            # 75% of 120 columns, leaving the sidebar visible.
            assert frame.size.width == pytest.approx(90, abs=2)
            # Banner and footer rows stay clear.
            assert frame.size.height < app.screen.size.height
            assert panel.size.width < app.screen.size.width


class TestClosing:
    async def test_q_closes_the_panel_and_librarian_survives(
        self, app, tmp_path, monkeypatch
    ):
        """remtui's panel binds `q` to quit, which would close Librarian."""
        async with app.run_test(size=(120, 38)) as pilot:
            await pilot.pause()
            await open_panel(app, pilot, tmp_path, monkeypatch)
            assert isinstance(app.screen, RemindersModal)

            await pilot.press("q")
            await pilot.pause()

            assert not isinstance(app.screen, RemindersModal)
            assert app.is_running

    async def test_closing_restores_the_folder_view(self, app, tmp_path, monkeypatch):
        async with app.run_test(size=(120, 38)) as pilot:
            await pilot.pause()
            tag_list = app.query_one(TagList)
            before = tag_list.active_source

            await open_panel(app, pilot, tmp_path, monkeypatch)
            await pilot.press("q")
            await pilot.pause()

            assert tag_list.active_source == before == "folders"
            assert tag_list.directory_tree.display


class TestKeyIsolation:
    """Librarian's own keys must not act while the panel is open.

    Librarian binds single letters on the App, which would otherwise stay live
    under another screen. ModalScreen stops that, and this pins it.
    """

    async def test_librarian_search_key_is_inert(self, app, tmp_path, monkeypatch):
        from librarian.widgets import FileList

        async with app.run_test(size=(120, 38)) as pilot:
            await pilot.pause()
            await open_panel(app, pilot, tmp_path, monkeypatch)

            await pilot.press("s")
            await pilot.pause()

            assert not app.query_one(FileList).is_search_mode()
            assert isinstance(app.screen, RemindersModal)

    async def test_n_reaches_the_panel_not_librarian(self, app, tmp_path, monkeypatch):
        """`n` is new-file in Librarian and add-reminder in remtui."""
        async with app.run_test(size=(120, 38)) as pilot:
            await pilot.pause()
            await open_panel(app, pilot, tmp_path, monkeypatch)

            await pilot.press("n")
            for _ in range(10):
                await pilot.pause()
                if type(app.screen).__name__ == "ReminderFormScreen":
                    break

            assert type(app.screen).__name__ == "ReminderFormScreen"
            # No stray note was created in the vault.
            assert list(app.config.scan_directory.glob("*.md")) == []


class TestPanelInteraction:
    async def test_a_opens_remtuis_add_form_on_top(self, app, tmp_path, monkeypatch):
        """The panel's own dialogs work, styles included, inside Librarian."""
        async with app.run_test(size=(120, 38)) as pilot:
            await pilot.pause()
            await open_panel(app, pilot, tmp_path, monkeypatch)

            await pilot.press("a")
            for _ in range(10):
                await pilot.pause()
                if type(app.screen).__name__ == "ReminderFormScreen":
                    break

            assert type(app.screen).__name__ == "ReminderFormScreen"
            # The dialog is styled, not raw: dialogs.tcss travelled with it.
            dialog = app.screen.query_one("#dialog")
            assert dialog.styles.background is not None

    async def test_filtering_narrows_the_list_inside_librarian(
        self, app, tmp_path, monkeypatch
    ):
        async with app.run_test(size=(120, 38)) as pilot:
            await pilot.pause()
            panel = await open_panel(app, pilot, tmp_path, monkeypatch)
            before = len(panel.reminders)

            await pilot.press("slash")
            for ch in "zzzz":  # matches nothing
                await pilot.press(ch)
            await pilot.pause()
            await pilot.pause()

            list_view = panel.query_one("#reminders")
            assert len(list_view.children) == 0
            assert before > 0
            assert app.is_running
