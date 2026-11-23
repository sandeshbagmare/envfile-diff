"""Tests for envfile_diff."""

import json

import pytest

from envfile_diff import (
    Change,
    EnvDiff,
    EnvParseError,
    diff_env,
    diff_files,
    parse_env,
    render,
)


class TestParseEnv:
    def test_simple_assignment(self):
        assert parse_env("A=1\n") == {"A": 1 and "1"}

    def test_several_keys_keep_their_order(self):
        assert list(parse_env("B=2\nA=1\n")) == ["B", "A"]

    def test_comments_and_blank_lines_are_skipped(self):
        assert parse_env("# note\n\nA=1\n   \n") == {"A": "1"}

    def test_export_prefix(self):
        assert parse_env("export A=1\n") == {"A": "1"}

    def test_spaces_around_the_equals_sign(self):
        assert parse_env("  A = 1  \n") == {"A": "1"}

    def test_empty_value(self):
        assert parse_env("A=\n") == {"A": ""}

    def test_double_quotes_keep_spaces_and_hashes(self):
        assert parse_env('A="hello # world"\n') == {"A": "hello # world"}

    def test_single_quotes_are_literal(self):
        assert parse_env("A='a \\n b'\n") == {"A": "a \\n b"}

    def test_escapes_inside_double_quotes(self):
        assert parse_env('A="line1\\nline2\\ttab"\n') == {"A": "line1\nline2\ttab"}

    def test_trailing_comment_after_an_unquoted_value(self):
        assert parse_env("A=1  # why\n") == {"A": "1"}

    def test_hash_inside_an_unquoted_value_is_kept(self):
        assert parse_env("A=a#b\n") == {"A": "a#b"}

    def test_crlf_input(self):
        assert parse_env("A=1\r\nB=2\r\n") == {"A": "1", "B": "2"}

    def test_later_value_wins(self):
        assert parse_env("A=1\nA=2\n") == {"A": "2"}

    def test_keys_with_dots_and_dashes(self):
        assert parse_env("DB.HOST=localhost\nMY-KEY=1\n") == {
            "DB.HOST": "localhost",
            "MY-KEY": "1",
        }

    def test_value_may_contain_equals_signs(self):
        assert parse_env("A=a=b\n") == {"A": "a=b"}

    def test_a_line_without_an_equals_sign_is_an_error(self):
        with pytest.raises(EnvParseError, match="line 1"):
            parse_env("NOPE\n")

    def test_an_invalid_key_is_an_error(self):
        with pytest.raises(EnvParseError, match="not a valid key"):
            parse_env("1BAD=1\n")

    def test_an_unterminated_quote_is_an_error(self):
        with pytest.raises(EnvParseError, match="unterminated"):
            parse_env('A="oops\n')

    def test_the_error_carries_the_line_number(self):
        with pytest.raises(EnvParseError) as info:
            parse_env("A=1\nB=2\nOOPS\n")
        assert info.value.line == 3

    def test_empty_document(self):
        assert parse_env("") == {}


class TestDiffEnv:
    def test_identical_files(self):
        diff = diff_env({"A": "1"}, {"A": "1"})
        assert diff.is_empty
        assert diff.unchanged == {"A": "1"}

    def test_added_and_removed(self):
        diff = diff_env({"OLD": "1"}, {"NEW": "2"})
        assert diff.added == {"NEW": "2"}
        assert diff.removed == {"OLD": "1"}
        assert not diff.is_empty

    def test_changed(self):
        diff = diff_env({"A": "1"}, {"A": "2"})
        assert diff.changed == {"A": ("1", "2")}

    def test_change_kinds(self):
        diff = diff_env({"GONE": "1", "SAME": "x"}, {"FRESH": "2", "SAME": "x"})
        assert [change.kind for change in diff.changes()] == ["added", "removed"]
        assert diff.keys() == ["FRESH", "GONE"]

    def test_changes_are_sorted(self):
        diff = diff_env({}, {"z": "1", "a": "2", "m": "3"})
        assert diff.keys() == ["a", "m", "z"]

    def test_unchanged_is_tracked_separately(self):
        diff = diff_env({"A": "1", "B": "2"}, {"A": "1", "B": "3"})
        assert diff.unchanged == {"A": "1"}

    def test_diffing_against_nothing(self):
        diff = diff_env({}, {"A": "1"})
        assert diff.keys() == ["A"]
        assert diff.removed == {}


class TestRender:
    def test_values_are_masked_by_default(self):
        text = render(diff_env({"A": "secret"}, {"A": "other"}))
        assert text == "~ A=*** (changed)"
        assert "secret" not in text

    def test_added_and_removed_lines(self):
        text = render(diff_env({"GONE": "x"}, {"FRESH": "y"}))
        assert text.splitlines() == ["+ FRESH=***", "- GONE=***"]

    def test_show_values(self):
        text = render(diff_env({"A": "1"}, {"A": "2"}), show_values=True)
        assert text == "~ A=1 -> 2"

    def test_a_custom_mask(self):
        assert render(diff_env({}, {"A": "1"}), mask="***redacted") == "+ A=***redacted"

    def test_unchanged_is_hidden_unless_asked(self):
        diff = diff_env({"A": "1"}, {"A": "1"})
        assert render(diff) == ""
        assert render(diff, include_unchanged=True) == "= A=***"

    def test_an_empty_diff_renders_nothing(self):
        assert render(EnvDiff()) == ""


class TestDiffFiles:
    def test_two_files_on_disk(self, tmp_path):
        older = tmp_path / "old.env"
        newer = tmp_path / "new.env"
        older.write_text("A=1\nB=2\n", encoding="utf-8")
        newer.write_text("B=3\nC=4\n", encoding="utf-8")
        diff = diff_files(older, newer)
        assert diff.keys() == ["A", "B", "C"]

    def test_a_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            diff_files(tmp_path / "nope.env", tmp_path / "nope2.env")


class TestChange:
    def test_added_change(self):
        assert Change("A", None, "1").kind == "added"

    def test_removed_change(self):
        assert Change("A", "1", None).kind == "removed"

    def test_changed_change(self):
        assert Change("A", "1", "2").kind == "changed"


class TestCommandLine:
    def run(self, argv):
        from envfile_diff.__main__ import main

        return main(argv)

    def files(self, tmp_path, old, new):
        older = tmp_path / "old.env"
        newer = tmp_path / "new.env"
        older.write_text(old, encoding="utf-8")
        newer.write_text(new, encoding="utf-8")
        return str(older), str(newer)

    def test_masked_output(self, tmp_path, capsys):
        older, newer = self.files(tmp_path, "A=secret\n", "B=other\n")
        assert self.run([older, newer]) == 0
        captured = capsys.readouterr()
        assert "secret" not in captured.out
        assert "+ B=***" in captured.out
        assert "1 added, 1 removed, 0 changed" in captured.err

    def test_show_values(self, tmp_path, capsys):
        older, newer = self.files(tmp_path, "A=1\n", "A=2\n")
        assert self.run([older, newer, "--show-values"]) == 0
        assert "~ A=1 -> 2" in capsys.readouterr().out

    def test_exit_code_flag(self, tmp_path):
        older, newer = self.files(tmp_path, "A=1\n", "A=2\n")
        assert self.run([older, newer, "--exit-code"]) == 1

    def test_exit_code_flag_with_identical_files(self, tmp_path):
        older, newer = self.files(tmp_path, "A=1\n", "A=1\n")
        assert self.run([older, newer, "--exit-code"]) == 0

    def test_json_output(self, tmp_path, capsys):
        older, newer = self.files(tmp_path, "A=1\n", "B=2\n")
        assert self.run([older, newer, "--json"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["added"] == ["B"]
        assert payload["removed"] == ["A"]

    def test_json_with_values(self, tmp_path, capsys):
        older, newer = self.files(tmp_path, "A=1\n", "A=2\n")
        assert self.run([older, newer, "--json", "--show-values"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["changed"] == {"A": ["1", "2"]}

    def test_include_unchanged(self, tmp_path, capsys):
        older, newer = self.files(tmp_path, "A=1\n", "A=1\n")
        assert self.run([older, newer, "--include-unchanged"]) == 0
        assert "= A=***" in capsys.readouterr().out

    def test_missing_file_exits_two(self, tmp_path, capsys):
        assert self.run([str(tmp_path / "a.env"), str(tmp_path / "b.env")]) == 2
        assert "no such file" in capsys.readouterr().err

    def test_a_broken_file_exits_two(self, tmp_path, capsys):
        older, newer = self.files(tmp_path, "OOPS\n", "A=1\n")
        assert self.run([older, newer]) == 2
        captured = capsys.readouterr()
        assert "KEY=VALUE" in captured.err


class TestRigour:
    """Branches behind the obvious ones: unmasked values and empty sides."""

    def test_show_values_prints_the_values(self):
        from envfile_diff import render

        diff = diff_env(parse_env("A=1\n"), parse_env("A=2\n"))
        assert "1" in render(diff, show_values=True)
        assert "2" in render(diff, show_values=True)

    def test_a_removed_key_renders_an_empty_side(self):
        from envfile_diff import render

        diff = diff_env(parse_env("A=1\n"), parse_env(""))
        assert render(diff) == "- A=***"

    def test_unchanged_lines_can_be_included(self):
        from envfile_diff import render

        diff = diff_env(parse_env("A=1\nB=2\n"), parse_env("A=1\n"))
        assert "= A=***" in render(diff, include_unchanged=True)

    def test_a_value_that_is_only_quotes(self):
        assert parse_env('A=""\n')["A"] == ""
        assert parse_env("A=''\n")["A"] == ""


class TestRigour2:
    """Values shown on both sides of a change, including the empty side."""

    def test_a_removed_key_with_values_shown(self):
        from envfile_diff import render

        diff = diff_env(parse_env("A=1\n"), parse_env(""))
        assert render(diff, show_values=True) == "- A=1"

    def test_an_added_key_with_values_shown(self):
        from envfile_diff import render

        diff = diff_env(parse_env(""), parse_env("A=1\n"))
        assert render(diff, show_values=True) == "+ A=1"
