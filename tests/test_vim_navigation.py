"""Tests for the optional vim keys: `ctrl+w` + h/j/k/l moves between panels.

The switch is `[keys] vim`, and "off changes nothing" is as much the contract as
the movement itself -- these keys are ordinary letters to everyone else.
"""

import pytest

from librarian.config import (
    CalendarConfig,
    Config,
    FoldersConfig,
    IconConfig,
    KeysConfig,
    ObsidianConfig,
    TagConfig,
    ToolsConfig,
)
from librarian.database import add_file, batch_writes
from librarian.widgets import FileList, TagList


@pytest.fixture
def vault(tmp_path):
    root = tmp_path / "vault"
    (root / "techne").mkdir(parents=True)
    # Three files at the root, so a list cursor has somewhere to go: with one
    # item, `j` and `G` pass whether or not they do anything.
    (root / "root-note.md").write_text("# root\n")
    (root / "second.md").write_text("# second\n")
    (root / "third.md").write_text("# third\n")
    (root / "techne" / "Alpha.md").write_text("# alpha #tagged\n")
    return root


@pytest.fixture
def config(vault, tmp_path):
    return Config(
        scan_directory=vault,
        editor="vim",
        tags=TagConfig(),
        export_directory=tmp_path / "exports",
        data_directory=tmp_path / "data",
        calendar=CalendarConfig(),
        icons=IconConfig(style="nerd"),
        folders=FoldersConfig(),
        obsidian=ObsidianConfig(),
        keys=KeysConfig(vim=True),
    )


@pytest.fixture
def make_app(config, tmp_index):
    """Build an app on the vim config, optionally adjusted first."""
    from librarian.app import LibrarianApp

    with batch_writes():
        add_file(config.scan_directory / "techne" / "Alpha.md", 1.0, ["tagged"])

    def build(**overrides):
        for key, value in overrides.items():
            setattr(config, key, value)
        return LibrarianApp(config)

    return build


@pytest.fixture
def app(make_app):
    return make_app()


def panels(app):
    """The four focusable panels, by name."""
    tag_list = app.query_one(TagList)
    return {
        "folders": tag_list.directory_tree,
        "tags": tag_list.all_tags_list_view,
        "files": app.query_one(FileList).list_view,
        "preview": app.query_one("#preview").scroll_view,
    }


class TestMovingWithinAColumn:
    async def test_down_from_folders_reaches_tags(self, app):
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            await pilot.press("ctrl+w", "j")
            await pilot.pause()

            assert app.focused is panels(app)["tags"]

    async def test_up_from_tags_reaches_folders(self, app):
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            panels(app)["tags"].focus()
            await pilot.pause()

            await pilot.press("ctrl+w", "k")
            await pilot.pause()

            assert app.focused is panels(app)["folders"]

    async def test_down_at_the_bottom_of_the_left_column_stays_put(self, app):
        """Tags is the last stop in the sidebar; launchers live in the strip."""
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            panels(app)["tags"].focus()
            await pilot.pause()

            await pilot.press("ctrl+w", "j")
            await pilot.pause()

            assert app.focused is panels(app)["tags"]

    async def test_up_at_the_top_stays_put(self, app):
        """vim does not wrap on ctrl+w k; Tab still does, and is untouched."""
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()

            await pilot.press("ctrl+w", "k")
            await pilot.pause()

            assert app.focused is panels(app)["folders"]

    async def test_down_at_the_bottom_of_the_right_column_stays_put(self, app):
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            panels(app)["preview"].focus()
            await pilot.pause()

            await pilot.press("ctrl+w", "j")
            await pilot.pause()

            assert app.focused is panels(app)["preview"]

    async def test_down_from_files_reaches_the_preview(self, app):
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            panels(app)["files"].focus()
            await pilot.pause()

            await pilot.press("ctrl+w", "j")
            await pilot.pause()

            assert app.focused is panels(app)["preview"]


class TestMovingBetweenColumns:
    async def test_right_from_folders_reaches_the_files_panel(self, app):
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()

            await pilot.press("ctrl+w", "l")
            await pilot.pause()

            assert app.focused is panels(app)["files"]

    async def test_left_comes_back_to_the_folder_tree(self, app):
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            panels(app)["files"].focus()
            await pilot.pause()

            await pilot.press("ctrl+w", "h")
            await pilot.pause()

            assert app.focused is panels(app)["folders"]

    async def test_the_column_remembers_where_you_were(self, app):
        """The rows do not line up, so `l` returns to the panel you left."""
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            panels(app)["preview"].focus()
            await pilot.pause()

            await pilot.press("ctrl+w", "h")
            await pilot.pause()
            assert app.focused is panels(app)["folders"]

            await pilot.press("ctrl+w", "l")
            await pilot.pause()
            assert app.focused is panels(app)["preview"]

    async def test_memory_follows_a_panel_reached_with_tab(self, app):
        """Tab is the other way to move, and must not desync the memory."""
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            panels(app)["tags"].focus()
            await pilot.pause()

            await pilot.press("ctrl+w", "l")
            await pilot.pause()
            await pilot.press("ctrl+w", "h")
            await pilot.pause()

            assert app.focused is panels(app)["tags"]

    async def test_left_in_the_left_column_stays_put(self, app):
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()

            await pilot.press("ctrl+w", "h")
            await pilot.pause()

            assert app.focused is panels(app)["folders"]

    async def test_a_remembered_panel_that_vanished_falls_back(self, app):
        """A remembered panel can be hidden or gone; the column must still be reachable."""
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            app._vim_column[0] = "craft-tree"  # not composed: craft is off
            panels(app)["files"].focus()
            await pilot.pause()

            await pilot.press("ctrl+w", "h")
            await pilot.pause()

            assert app.focused is panels(app)["folders"]


class TestThePrefix:
    async def test_a_bare_direction_key_does_not_move_panels(self, app):
        """Without the prefix these keys belong to the focused widget."""
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()

            await pilot.press("j")
            await pilot.pause()

            assert app.focused is panels(app)["folders"]

    async def test_the_prefix_is_spent_by_one_move(self, app):
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()

            await pilot.press("ctrl+w", "j", "j")
            await pilot.pause()

            assert app._vim_pending is False
            assert app.focused is panels(app)["tags"]

    async def test_the_prefix_expires(self, app):
        """A forgotten ctrl+w must not silently rearm the keys minutes later."""
        app.VIM_PREFIX_TIMEOUT = 0.05
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()

            await pilot.press("ctrl+w")
            await pilot.pause(0.15)
            assert app._vim_pending is False

            await pilot.press("j")
            await pilot.pause()
            assert app.focused is panels(app)["folders"]


class TestTheSwitch:
    async def test_nothing_moves_when_vim_is_off(self, make_app):
        app = make_app(keys=KeysConfig(vim=False))
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()

            await pilot.press("ctrl+w", "j")
            await pilot.pause()

            assert app._vim_pending is False
            assert app.focused is panels(app)["folders"]

    async def test_the_bindings_report_themselves_disabled(self, make_app):
        app = make_app(keys=KeysConfig(vim=False))
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()

            assert app.check_action("vim_prefix", ()) is False
            assert app.check_action("vim_focus", ("down",)) is False
            # Unrelated actions are untouched by the override.
            assert app.check_action("search", ()) is not False

    async def test_tab_still_walks_the_flat_order(self, app):
        """The vim keys are additive: Tab keeps wrapping, vim keys do not."""
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            panels(app)["preview"].focus()
            await pilot.pause()

            await pilot.press("tab")
            await pilot.pause()

            assert app.focused is panels(app)["folders"]


class TestInsideAPanel:
    async def test_j_and_k_move_the_folder_tree_cursor(self, app):
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            tree = panels(app)["folders"]
            tree.root.expand()
            await pilot.pause()

            await pilot.press("j")
            await pilot.pause()
            assert tree.cursor_line == 1

            await pilot.press("k")
            await pilot.pause()
            assert tree.cursor_line == 0

    async def test_j_moves_a_list_cursor(self, app):
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            files = panels(app)["files"]
            files.focus()
            await pilot.pause()
            assert len(files.children) >= 2, "fixture must list several files"

            start = files.index
            await pilot.press("j")
            await pilot.pause()

            assert files.index == start + 1

    async def test_G_and_g_jump_to_the_ends_of_a_list(self, app):
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            files = panels(app)["files"]
            files.focus()
            await pilot.pause()
            last = len(files.children) - 1
            assert last > 0, "fixture must list several files"

            await pilot.press("G")
            await pilot.pause()
            assert files.index == last

            await pilot.press("g")
            await pilot.pause()
            assert files.index == 0

    async def test_j_scrolls_the_preview(self, app, vault):
        long_note = vault / "long.md"
        long_note.write_text("# long\n\n" + "\n\n".join(f"para {i}" for i in range(200)))

        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            preview = app.query_one("#preview")
            await preview.show_file(long_note)
            await pilot.pause()
            scroll = panels(app)["preview"]
            scroll.focus()
            await pilot.pause()

            await pilot.press("j")
            await pilot.pause()
            assert scroll.scroll_offset.y > 0

            await pilot.press("G")
            await pilot.pause()
            assert scroll.scroll_offset.y == scroll.max_scroll_y

    async def test_l_expands_a_folder_and_h_collapses_it(self, app):
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            tree = panels(app)["folders"]
            tree.root.expand()
            await pilot.pause()
            tree.move_cursor(next(
                node for node in tree.root.children if node.data.path.is_dir()
            ))
            await pilot.pause()
            node = tree.cursor_node

            await pilot.press("l")
            await pilot.pause()
            assert node.is_expanded

            await pilot.press("h")
            await pilot.pause()
            assert not node.is_expanded

    async def test_h_on_a_collapsed_folder_steps_out_to_the_parent(self, app):
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            tree = panels(app)["folders"]
            tree.root.expand()
            await pilot.pause()
            child = next(
                node for node in tree.root.children if node.data.path.is_dir()
            )
            tree.move_cursor(child)
            await pilot.pause()

            await pilot.press("h")
            await pilot.pause()

            assert tree.cursor_node is tree.root

    async def test_typing_in_the_search_box_is_not_navigation(self, app):
        """Input swallows printable keys, which is what keeps `s` usable."""
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            await pilot.press("s")
            await pilot.pause()

            await pilot.press("h", "j", "k", "l")
            await pilot.pause()

            search = app.query_one(FileList).search_input
            assert search.value == "hjkl"
            assert app.focused is search

    async def test_the_cursor_keys_are_inert_when_vim_is_off(self, make_app):
        app = make_app(keys=KeysConfig(vim=False))
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            tree = panels(app)["folders"]
            tree.root.expand()
            await pilot.pause()

            await pilot.press("j")
            await pilot.pause()

            assert tree.cursor_line == 0

    async def test_the_prefix_still_wins_over_the_cursor(self, app):
        """Both meanings live on `j`; ctrl+w decides which one fires."""
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            tree = panels(app)["folders"]
            tree.root.expand()
            await pilot.pause()

            await pilot.press("ctrl+w", "j")
            await pilot.pause()

            assert app.focused is panels(app)["tags"]
            assert tree.cursor_line == 0


class TestHelp:
    async def test_help_lists_the_vim_keys_when_they_are_on(self, app):
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            shown = []
            app.notify = lambda message, **kwargs: shown.append(message)

            app.action_help()

            assert "ctrl+w" in shown[0]

    async def test_help_does_not_advertise_keys_that_do_nothing(self, make_app):
        app = make_app(keys=KeysConfig(vim=False))
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            shown = []
            app.notify = lambda message, **kwargs: shown.append(message)

            app.action_help()

            assert "ctrl+w" not in shown[0]


class TestModals:
    async def test_a_modal_screen_keeps_the_keys_to_itself(self, app):
        """The guest panels carry their own keys; ours stop at the boundary."""
        from textual.screen import ModalScreen

        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            app.push_screen(ModalScreen())
            await pilot.pause()

            await pilot.press("ctrl+w", "j")
            await pilot.pause()

            assert app.focused is None
            assert app._vim_pending is False
