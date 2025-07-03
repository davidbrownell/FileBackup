# ----------------------------------------------------------------------
# |
# |  EntryPoint_UnitTest.py
# |
# |  David Brownell <db@DavidBrownell.com>
# |      2024-07-12 10:35:31
# |
# ----------------------------------------------------------------------
# |
# |  Copyright David Brownell 2024
# |  Distributed under the MIT License.
# |
# ----------------------------------------------------------------------
"""Unit tests for EntryPoint.py"""

import re
import uuid

from pathlib import Path
from unittest.mock import patch

import pytest

from dbrownell_Common.Streams.DoneManager import DoneManager
from dbrownell_Common.TestHelpers.StreamTestHelpers import InitializeStreamCapabilities
from typer.testing import CliRunner

from FileBackup import __version__
from FileBackup.CommandLine.EntryPoint import app
from FileBackup.Mirror import ValidateType
from FileBackup.Offsite import DEFAULT_ARCHIVE_VOLUME_SIZE


# ----------------------------------------------------------------------
_this_file = Path(__file__)


@pytest.fixture(InitializeStreamCapabilities(), scope="session", autouse=True)

# ----------------------------------------------------------------------
def test_Version():
    result = CliRunner().invoke(app, ["version"])

    assert result.exit_code == 0
    assert result.output == f"FileBackup v{__version__}\n"


# ----------------------------------------------------------------------
def test_Help():
    result = CliRunner().invoke(app, "--help")

    assert result.exit_code == 0
    assert "Tools to backup and restore files and directories." in result.output
    assert "version" in result.output
    assert "mirror" in result.output
    assert "offsite" in result.output


# ----------------------------------------------------------------------
class TestMirror:
    class TestExecute:
        # ----------------------------------------------------------------------
        def test_Standard(self, tmp_path):
            with patch("FileBackup.Mirror.Backup") as backup:
                result = CliRunner().invoke(
                    app,
                    [
                        "mirror",
                        "execute",
                        str(tmp_path),
                        str(_this_file.parent),
                    ],
                )

                assert result.exit_code == 0

                args = backup.call_args_list[0].args

                assert isinstance(args[0], DoneManager), args[0]
                assert args[1] == str(tmp_path), args[1]
                assert args[2] == [_this_file.parent], args[2]

                kwargs = backup.call_args_list[0].kwargs

                assert kwargs == {
                    "ssd": False,
                    "force": False,
                    "quiet": False,
                    "file_includes": [],
                    "file_excludes": [],
                }

        # ----------------------------------------------------------------------
        def test_WithFlags(self, tmp_path):
            with patch("FileBackup.Mirror.Backup") as backup:
                result = CliRunner().invoke(
                    app,
                    [
                        "mirror",
                        "execute",
                        str(tmp_path),
                        str(_this_file.parent),
                        "--ssd",
                        "--force",
                        "--quiet",
                        "--file-include",
                        "one",
                        "--file-include",
                        "two",
                        "--file-exclude",
                        "three",
                        "--file-exclude",
                        "four",
                        "--file-exclude",
                        "five",
                    ],
                )

                assert result.exit_code == 0

                args = backup.call_args_list[0].args

                assert isinstance(args[0], DoneManager), args[0]
                assert args[1] == str(tmp_path), args[1]
                assert args[2] == [_this_file.parent], args[2]

                kwargs = backup.call_args_list[0].kwargs

                assert kwargs == {
                    "ssd": True,
                    "force": True,
                    "quiet": True,
                    "file_includes": [re.compile("^one$"), re.compile("^two$")],
                    "file_excludes": [
                        re.compile("^three$"),
                        re.compile("^four$"),
                        re.compile("^five$"),
                    ],
                }

        # ----------------------------------------------------------------------
        def test_ErrorBadRegex(self, tmp_path):
            expression = "(?:not_valid"

            result = CliRunner().invoke(
                app,
                [
                    "mirror",
                    "execute",
                    str(tmp_path),
                    str(_this_file.parent),
                    "--file-include",
                    expression,
                ],
            )

            assert result.exit_code != 0
            assert f"The regular expression '{expression}' is not valid" in result.output

        # ----------------------------------------------------------------------
        def test_Help(self):
            result = CliRunner().invoke(app, ["mirror", "execute", "--help"])

            assert result.exit_code == 0

            assert "Mirrors content to a backup data store." in result.output
            assert "Data Store Destinations" in result.output

    # ----------------------------------------------------------------------
    class TestValidate:
        # ----------------------------------------------------------------------
        def test_Standard(self, tmp_path):
            with patch("FileBackup.Mirror.Validate") as validate:
                result = CliRunner().invoke(app, ["mirror", "validate", str(tmp_path)])

                assert result.exit_code == 0

                args = validate.call_args_list[0].args

                assert isinstance(args[0], DoneManager), args[0]
                assert args[1] == str(tmp_path), args[1]
                assert args[2] == ValidateType.standard, args[2]

                kwargs = validate.call_args_list[0].kwargs

                assert kwargs == {
                    "ssd": False,
                    "quiet": False,
                }

        # ----------------------------------------------------------------------
        def test_WithFlags(self, tmp_path):
            with patch("FileBackup.Mirror.Validate") as validate:
                result = CliRunner().invoke(
                    app,
                    [
                        "mirror",
                        "validate",
                        str(tmp_path),
                        ValidateType.complete.name,
                        "--ssd",
                        "--quiet",
                    ],
                )

                assert result.exit_code == 0

                args = validate.call_args_list[0].args

                assert isinstance(args[0], DoneManager), args[0]
                assert args[1] == str(tmp_path), args[1]
                assert args[2] == ValidateType.complete, args[2]

                kwargs = validate.call_args_list[0].kwargs

                assert kwargs == {
                    "ssd": True,
                    "quiet": True,
                }

        # ----------------------------------------------------------------------
        def test_Help(self):
            result = CliRunner().invoke(app, ["mirror", "validate", "--help"])

            assert result.exit_code == 0

            assert "Validates previously mirrored content in the backup data store." in result.output
            assert "Data Store Destinations" in result.output

    # ----------------------------------------------------------------------
    class TestCleanup:
        # ----------------------------------------------------------------------
        def test_Standard(self, tmp_path):
            with patch("FileBackup.Mirror.Cleanup") as cleanup:
                result = CliRunner().invoke(app, ["mirror", "cleanup", str(tmp_path)])

                assert result.exit_code == 0

                args = cleanup.call_args_list[0].args

                assert isinstance(args[0], DoneManager), args[0]
                assert args[1] == str(tmp_path), args[1]

                kwargs = cleanup.call_args_list[0].kwargs

                assert kwargs == {}

        # ----------------------------------------------------------------------
        def test_Help(self):
            result = CliRunner().invoke(app, ["mirror", "cleanup", "--help"])

            assert result.exit_code == 0

            assert (
                "Cleans a backup data store after a mirror execution that was interrupted or failed."
                in result.output
            )
            assert "Data Store Destinations" in result.output


# ----------------------------------------------------------------------
class TestOffsite:
    # ----------------------------------------------------------------------
    class TestExecute:
        # ----------------------------------------------------------------------
        def test_Standard(self, tmp_path):
            with patch("FileBackup.Offsite.Backup") as backup:
                result = CliRunner().invoke(
                    app,
                    [
                        "offsite",
                        "execute",
                        "BackupName",
                        str(tmp_path),
                        str(_this_file.parent),
                    ],
                )

                assert result.exit_code == 0

                args = backup.call_args_list[0].args

                assert isinstance(args[0], DoneManager), args[0]
                assert args[1] == "BackupName", args[1]
                assert args[2] == str(tmp_path), args[2]
                assert args[3] == [_this_file.parent], args[3]
                assert args[4] is None, args[4]  # encryption password
                assert isinstance(args[5], Path), args[5]  # working dir

                kwargs = backup.call_args_list[0].kwargs

                assert kwargs == {
                    "compress": False,
                    "ssd": False,
                    "force": False,
                    "quiet": False,
                    "file_includes": [],
                    "file_excludes": [],
                    "archive_volume_size": DEFAULT_ARCHIVE_VOLUME_SIZE,
                    "ignore_pending_snapshot": False,
                }

        # ----------------------------------------------------------------------
        def test_WithFlags(self, tmp_path):
            with patch("FileBackup.Offsite.Backup") as backup:
                backup_name = str(uuid.uuid4())
                encryption_password = str(uuid.uuid4())
                working_dir = tmp_path / "working_dir"
                archive_volume_size = DEFAULT_ARCHIVE_VOLUME_SIZE // 2

                result = CliRunner().invoke(
                    app,
                    [
                        "offsite",
                        "execute",
                        backup_name,
                        str(tmp_path),
                        str(_this_file.parent),
                        "--encryption-password",
                        encryption_password,
                        "--compress",
                        "--ssd",
                        "--force",
                        "--quiet",
                        "--working-dir",
                        working_dir,
                        "--archive-volume-size",
                        str(archive_volume_size),
                        "--ignore-pending-snapshot",
                        "--file-include",
                        "one",
                        "--file-include",
                        "two",
                        "--file-exclude",
                        "three",
                        "--file-exclude",
                        "four",
                        "--file-exclude",
                        "five",
                    ],
                )

                assert result.exit_code == 0

                args = backup.call_args_list[0].args

                assert isinstance(args[0], DoneManager), args[0]
                assert args[1] == backup_name, args[1]
                assert args[2] == str(tmp_path), args[2]
                assert args[3] == [_this_file.parent], args[3]
                assert args[4] == encryption_password, args[4]
                assert args[5] == working_dir, args[5]

                kwargs = backup.call_args_list[0].kwargs

                assert kwargs == {
                    "compress": True,
                    "ssd": True,
                    "force": True,
                    "quiet": True,
                    "file_includes": [re.compile("^one$"), re.compile("^two$")],
                    "file_excludes": [
                        re.compile("^three$"),
                        re.compile("^four$"),
                        re.compile("^five$"),
                    ],
                    "archive_volume_size": archive_volume_size,
                    "ignore_pending_snapshot": True,
                }

        # ----------------------------------------------------------------------
        def test_ErrorBadRegex(self, tmp_path):
            expression = "(?:not_valid"

            result = CliRunner().invoke(
                app,
                [
                    "offsite",
                    "execute",
                    "BackupName",
                    str(tmp_path),
                    str(_this_file.parent),
                    "--file-include",
                    expression,
                ],
            )

            assert result.exit_code != 0
            assert f"The regular expression '{expression}' is not valid" in result.output

        # ----------------------------------------------------------------------
        def test_Help(self):
            result = CliRunner().invoke(app, ["offsite", "execute", "--help"])

            assert result.exit_code == 0

            assert "Prepares local changes for offsite backup." in result.output
            assert "Data Store Destinations" in result.output

    # ----------------------------------------------------------------------
    class TestCommit:
        # ----------------------------------------------------------------------
        def test_Standard(self, tmp_path):
            with patch("FileBackup.Offsite.Commit") as commit:
                result = CliRunner().invoke(app, ["offsite", "commit", "BackupName"])

                assert result.exit_code == 0

                args = commit.call_args_list[0].args

                assert isinstance(args[0], DoneManager), args[0]
                assert args[1] == "BackupName", args[1]

                kwargs = commit.call_args_list[0].kwargs

                assert kwargs == {}

        # ----------------------------------------------------------------------
        def test_Help(self):
            result = CliRunner().invoke(app, ["offsite", "commit", "--help"])

            assert result.exit_code == 0

            assert (
                "Commits a pending snapshot after the changes have been transferred to an offsite data store."
                in result.output
            )

    # ----------------------------------------------------------------------
    class TestRestore:
        # ----------------------------------------------------------------------
        def test_Standard(self, tmp_path):
            with patch("FileBackup.Offsite.Restore") as restore:
                result = CliRunner().invoke(app, ["offsite", "restore", "BackupName", str(tmp_path)])

                assert result.exit_code == 0

                args = restore.call_args_list[0].args

                assert isinstance(args[0], DoneManager), args[0]
                assert args[1] == "BackupName", args[1]
                assert args[2] == str(tmp_path), args[2]
                assert args[3] is None, args[3]  # encryption password
                assert isinstance(args[4], Path), args[4]  # working dir
                assert args[5] == {}

                kwargs = restore.call_args_list[0].kwargs

                assert kwargs == {
                    "continue_on_errors": False,
                    "ssd": False,
                    "quiet": False,
                    "dry_run": False,
                    "overwrite": False,
                }

        # ----------------------------------------------------------------------
        def test_WithFlags(self, tmp_path):
            with patch("FileBackup.Offsite.Restore") as restore:
                backup_name = str(uuid.uuid4())
                encryption_password = str(uuid.uuid4())
                working_dir = tmp_path / "working_dir"
                dir_subs = {
                    "one": "two",
                    "three": "four",
                }

                args = [
                    "offsite",
                    "restore",
                    backup_name,
                    str(tmp_path),
                    "--working-dir",
                    working_dir,
                    "--encryption-password",
                    encryption_password,
                ]

                for k, v in dir_subs.items():
                    args += ["--dir-substitution", f"{k}:{v}"]

                args += [
                    "--dry-run",
                    "--overwrite",
                    "--ssd",
                    "--quiet",
                    "--continue-on-errors",
                ]

                result = CliRunner().invoke(app, args)

                assert result.exit_code == 0

                args = restore.call_args_list[0].args

                assert isinstance(args[0], DoneManager), args[0]
                assert args[1] == backup_name, args[1]
                assert args[2] == str(tmp_path), args[2]
                assert args[3] == encryption_password, args[3]
                assert args[4] == working_dir, args[4]
                assert args[5] == dir_subs

                kwargs = restore.call_args_list[0].kwargs

                assert kwargs == {
                    "continue_on_errors": True,
                    "ssd": True,
                    "quiet": True,
                    "dry_run": True,
                    "overwrite": True,
                }

        # ----------------------------------------------------------------------
        def test_Help(self):
            result = CliRunner().invoke(app, ["offsite", "restore", "--help"])

            assert result.exit_code == 0

            assert "Restores content from an offsite data store." in result.output
            assert "Data Store Destinations" in result.output
