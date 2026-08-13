"""Tests for the calendar modal.

Calendar used to live in the sidebar, sharing a panel with Folders and Tags. Now
that those two are permanent it opens as a modal over the right-hand panels, the
same shape the Reminders panel uses. These tests cover the framing rather than
the parsing -- `test_calendar.py` owns the icalPal side.

Nothing here touches the real calendar: `fetch_todays_events` is patched, so
`action_open_calendar` gets a deterministic list (or a deterministic failure).
"""

from __future__ import annotations

import pytest

from librarian.calendar import CalendarError
from librarian.config import CalendarConfig, Config, TagConfig, ToolsConfig
from librarian.widgets import FileList, TagList
from librarian.widgets.calendar_modal import CalendarModal
from tests.test_calendar import _parse_event, raw_event


@pytest.fixture
def config(tmp_path):
    root = tmp_path / "notes"
    root.mkdir()
    (root / "Standup Notes.md").write_text("# Standup\n\n#meetings\n")
    return Config(
        scan_directory=root,
        editor="vim",
        tags=TagConfig(),
        export_directory=tmp_path / "exports",
        data_directory=tmp_path / "data",
        calendar=CalendarConfig(),
        tools=ToolsConfig(calendar=True),
    )


@pytest.fixture
def app(config, tmp_path, tmp_index):
    from librarian.app import LibrarianApp
    from librarian.calendar_store import init_store

    init_store(tmp_path / "store")
    return LibrarianApp(config)


@pytest.fixture
def events(monkeypatch):
    """Make the fetch worker return one meeting instead of shelling out."""
    event = _parse_event(raw_event(title="Standup", location="Room 1"))
    monkeypatch.setattr(
        "librarian.actions.calendar_actions.fetch_todays_events",
        lambda *a, **kw: [event],
    )
    return [event]


async def open_modal(app, pilot) -> CalendarModal:
    """Open the modal and wait for the fetch worker to land."""
    app.action_open_calendar()
    for _ in range(20):
        await pilot.pause()
        if isinstance(app.screen, CalendarModal) and app.screen.calendar_list._events:
            break
    assert isinstance(app.screen, CalendarModal)
    return app.screen


class TestOpening:
    async def test_the_tool_opens_the_modal_with_todays_meetings(
        self, app, events, pilot_size=(100, 40)
    ):
        async with app.run_test(size=pilot_size) as pilot:
            await pilot.pause()
            modal = await open_modal(app, pilot)

            assert [e.title for e in modal.calendar_list._events] == ["Standup"]

    async def test_selecting_calendar_in_the_tools_menu_opens_it(self, app, events):
        """The Tools menu is the user's route in, not just the action."""
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            tag_list = app.query_one(TagList)

            names = [
                str(item.query_one("Static").render())
                for item in tag_list.tools_list_view.children
            ]
            assert "Calendar" in names

            tag_list.tools_list_view.focus()
            tag_list.tools_list_view.index = names.index("Calendar")
            await pilot.pause()
            await pilot.press("enter")
            for _ in range(20):
                await pilot.pause()
                if isinstance(app.screen, CalendarModal):
                    break

            assert isinstance(app.screen, CalendarModal)

    async def test_fetch_failure_is_shown_in_the_modal(self, app, monkeypatch):
        """An empty day and a broken icalPal must not look the same."""

        def boom(*args, **kwargs):
            raise CalendarError("icalPal not found")

        monkeypatch.setattr(
            "librarian.actions.calendar_actions.fetch_todays_events", boom
        )

        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            app.action_open_calendar()
            for _ in range(20):
                await pilot.pause()
                if isinstance(app.screen, CalendarModal):
                    break

            modal = app.screen
            # The fetch runs in a thread worker, so poll rather than waiting on
            # the worker set -- Librarian's watcher worker never completes.
            for _ in range(40):
                await pilot.pause()
                if "icalPal" in str(modal.calendar_list.status_label.render()):
                    break

            assert "icalPal not found" in str(modal.calendar_list.status_label.render())
            assert modal.calendar_list._events == []


class TestClosing:
    @pytest.mark.parametrize("key", ["q", "escape"])
    async def test_key_closes_the_modal_without_quitting_librarian(
        self, app, events, key
    ):
        """Closing the calendar must not close Librarian.

        Librarian binds `q` to quit at app level, so the modal has to claim the
        key first. It does -- a modal screen is checked before the app -- but
        that is exactly the kind of thing a refactor breaks silently.
        """
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            await open_modal(app, pilot)

            await pilot.press(key)
            for _ in range(10):
                await pilot.pause()
                if not isinstance(app.screen, CalendarModal):
                    break

            assert not isinstance(app.screen, CalendarModal)
            assert app.is_running

    async def test_closing_leaves_the_files_panel_as_it_was(self, app, events):
        """The modal covers the Files panel; it must not rewrite it."""
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            tag_list = app.query_one(TagList)
            file_list = app.query_one(FileList)

            before_header = file_list.get_header_text()
            before_source = tag_list.active_source

            await open_modal(app, pilot)
            await pilot.press("q")
            for _ in range(10):
                await pilot.pause()

            assert file_list.get_header_text() == before_header
            assert tag_list.active_source == before_source


class TestWatcherDuringTeardown:
    """The watcher thread can fire after the panels are gone.

    Creating a meeting note writes into the scan directory, so the debounced
    watcher callback can land during shutdown -- which used to raise `NoMatches`
    out of a `call_from_thread` future.
    """

    async def test_a_file_change_after_teardown_is_ignored(self, app):
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()

        # The app is unmounted; its widgets are gone.
        app._handle_file_change()


class TestForwardedBindings:
    """A modal screen stops the app's bindings, so the modal re-declares the
    keys the calendar needs. A missing forward is silent -- the key just does
    nothing -- which is what these assert against.
    """

    def test_the_modal_forwards_the_meeting_keys_to_the_app(self):
        bindings = {b.key: b.action for b in CalendarModal.BINDINGS}
        assert bindings["a"] == "app.associate_meeting"
        assert bindings["n"] == "app.new_file"
        assert bindings["e"] == "app.edit"
        assert bindings["q,escape"] == "close"

    async def test_the_modal_owns_q_and_hides_librarians_own_keys(self, app, events):
        """Pins what the modal does to the key map while it is open."""
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            await open_modal(app, pilot)

            active = app.active_bindings
            assert active["q"].binding.action == "close"
            assert active["escape"].binding.action == "close"
            # App-level bindings are stopped by the modal, which is why a/n/e
            # have to be forwarded -- these two are not, and go quiet.
            assert "s" not in active
            assert "d" not in active

    async def test_a_opens_the_associate_picker(self, app, events, monkeypatch):
        from librarian.widgets.file_info import AssociateModal

        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            modal = await open_modal(app, pilot)
            modal.calendar_list.list_view.index = 0
            await pilot.pause()

            await pilot.press("a")
            for _ in range(15):
                await pilot.pause()
                if isinstance(app.screen, AssociateModal):
                    break

            assert isinstance(app.screen, AssociateModal)

    async def test_n_creates_a_meeting_note_associated_with_the_event(
        self, app, events, config, monkeypatch
    ):
        """`n` writes the note, associates it, and hands it to the editor.

        The editor is stubbed out: the real one suspends the app.
        """
        opened: list = []

        async def fake_edit(self, path):
            opened.append(path)

        monkeypatch.setattr(
            "librarian.actions.file_actions.FileActionsMixin._edit_file", fake_edit
        )

        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            modal = await open_modal(app, pilot)
            modal.calendar_list.list_view.index = 0
            await pilot.pause()

            await pilot.press("n")
            # Waiting for the *condition* rather than a fixed number of pauses:
            # the note is written by a worker, and a count that is enough on an
            # idle machine loses the race under a full suite run.
            created: list = []
            for _ in range(50):
                await pilot.pause()
                created = list(config.scan_directory.glob("*-Standup.md"))
                if created and opened:
                    break

            assert created, "pressing n in the calendar should write a meeting note"
            body = created[0].read_text()
            assert "#meetings" in body
            assert "Standup" in body
            assert opened == created, "the new note should be handed to the editor"

            from librarian.calendar_store import get_association

            assert get_association(events[0].uid) == created[0]
