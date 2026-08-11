"""Tests for reading folder appearance from Notebook Navigator's plugin data."""

import json

import pytest

from librarian.obsidian import (
    PLUGIN_DATA_RELATIVE_PATH,
    NotebookNavigatorAppearance,
    find_vault_root,
)


def make_vault(root, data=None):
    """Create a vault skeleton, optionally with Notebook Navigator data."""
    (root / ".obsidian").mkdir(parents=True, exist_ok=True)
    if data is not None:
        data_path = root / PLUGIN_DATA_RELATIVE_PATH
        data_path.parent.mkdir(parents=True, exist_ok=True)
        data_path.write_text(json.dumps(data))
    return root


SAMPLE_DATA = {
    "showFolderIcons": True,
    "inheritFolderColors": True,
    "folderIcons": {
        "anthologia": "library",
        "kybernetes": "emoji:\U0001f916",
        "techne": "computer",
    },
    "folderColors": {
        "anthologia": "#78716c",
        "kybernetes": "#06b6d4",
    },
    "tagColors": {"arete": "#84cc16"},
}


class TestFindVaultRoot:
    def test_finds_vault_at_path(self, tmp_path):
        vault = make_vault(tmp_path / "vault")
        assert find_vault_root(vault) == vault.resolve()

    def test_walks_up_from_subdirectory(self, tmp_path):
        vault = make_vault(tmp_path / "vault")
        nested = vault / "techne" / "deep"
        nested.mkdir(parents=True)
        assert find_vault_root(nested) == vault.resolve()

    def test_returns_none_outside_vault(self, tmp_path):
        plain = tmp_path / "plain"
        plain.mkdir()
        assert find_vault_root(plain) is None


class TestLoad:
    def test_returns_none_when_not_a_vault(self, tmp_path):
        plain = tmp_path / "plain"
        plain.mkdir()
        assert NotebookNavigatorAppearance.load(plain) is None

    def test_returns_none_when_plugin_missing(self, tmp_path):
        vault = make_vault(tmp_path / "vault")
        assert NotebookNavigatorAppearance.load(vault) is None

    def test_returns_none_on_invalid_json(self, tmp_path):
        vault = make_vault(tmp_path / "vault")
        data_path = vault / PLUGIN_DATA_RELATIVE_PATH
        data_path.parent.mkdir(parents=True, exist_ok=True)
        data_path.write_text("{not valid json")
        assert NotebookNavigatorAppearance.load(vault) is None

    def test_returns_none_when_data_is_not_an_object(self, tmp_path):
        vault = make_vault(tmp_path / "vault", ["not", "a", "dict"])
        assert NotebookNavigatorAppearance.load(vault) is None

    def test_partial_data_uses_defaults(self, tmp_path):
        """A data.json without the appearance keys must still load."""
        vault = make_vault(tmp_path / "vault", {"dualPane": True})
        appearance = NotebookNavigatorAppearance.load(vault)

        assert appearance is not None
        assert appearance.folder_icons == {}
        assert appearance.folder_colors == {}
        assert appearance.inherit_folder_colors is True
        assert appearance.show_folder_icons is True
        assert appearance.color_icon_only is False

    def test_loads_icons_and_colors(self, tmp_path):
        vault = make_vault(tmp_path / "vault", SAMPLE_DATA)
        appearance = NotebookNavigatorAppearance.load(vault)

        assert appearance is not None
        assert appearance.vault_root == vault.resolve()
        assert appearance.folder_icons["anthologia"] == "library"
        assert appearance.folder_colors["kybernetes"] == "#06b6d4"
        assert appearance.tag_colors == {"arete": "#84cc16"}

    def test_loads_from_subdirectory_scan_root(self, tmp_path):
        vault = make_vault(tmp_path / "vault", SAMPLE_DATA)
        nested = vault / "techne"
        nested.mkdir()
        appearance = NotebookNavigatorAppearance.load(nested)

        assert appearance is not None
        # Keys stay relative to the vault root, not the scan directory.
        assert appearance.icon_name_for(nested) == "computer"

    def test_ignores_non_string_and_blank_values(self, tmp_path):
        vault = make_vault(
            tmp_path / "vault",
            {"folderColors": {"a": "#fff", "b": 42, "c": "", "d": None}},
        )
        appearance = NotebookNavigatorAppearance.load(vault)

        assert appearance is not None
        assert appearance.folder_colors == {"a": "#fff"}


class TestLookups:
    @pytest.fixture
    def appearance(self, tmp_path):
        vault = make_vault(tmp_path / "vault", SAMPLE_DATA)
        return NotebookNavigatorAppearance.load(vault)

    def test_icon_name_for_folder(self, appearance):
        assert appearance.icon_name_for(appearance.vault_root / "anthologia") == "library"

    def test_emoji_icon_returned_verbatim(self, appearance):
        assert (
            appearance.icon_name_for(appearance.vault_root / "kybernetes")
            == "emoji:\U0001f916"
        )

    def test_icon_name_for_unstyled_folder_is_none(self, appearance):
        assert appearance.icon_name_for(appearance.vault_root / "veritas") is None

    def test_icon_name_for_vault_root_is_none(self, appearance):
        assert appearance.icon_name_for(appearance.vault_root) is None

    def test_icon_name_for_path_outside_vault_is_none(self, appearance, tmp_path):
        assert appearance.icon_name_for(tmp_path / "elsewhere") is None

    def test_icons_suppressed_when_show_folder_icons_off(self, appearance):
        appearance.show_folder_icons = False
        assert appearance.icon_name_for(appearance.vault_root / "anthologia") is None

    def test_color_for_folder(self, appearance):
        assert appearance.color_for(appearance.vault_root / "anthologia") == "#78716c"

    def test_color_inherited_by_descendants(self, appearance):
        nested = appearance.vault_root / "anthologia" / "greek" / "epigrams"
        assert appearance.color_for(nested) == "#78716c"

    def test_nearest_ancestor_color_wins(self, appearance):
        appearance.folder_colors["anthologia/greek"] = "#123456"
        nested = appearance.vault_root / "anthologia" / "greek" / "epigrams"
        assert appearance.color_for(nested) == "#123456"

    def test_inheritance_disabled(self, appearance):
        appearance.inherit_folder_colors = False
        assert appearance.color_for(appearance.vault_root / "anthologia" / "greek") is None

    def test_color_for_unstyled_folder_is_none(self, appearance):
        assert appearance.color_for(appearance.vault_root / "veritas") is None

    def test_color_for_vault_root_is_none(self, appearance):
        assert appearance.color_for(appearance.vault_root) is None
