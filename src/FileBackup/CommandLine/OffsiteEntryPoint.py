# ----------------------------------------------------------------------
# |
# |  OffsiteEntryPoint.py
# |
# |  David Brownell <db@DavidBrownell.com>
# |      2024-07-04 12:51:52
# |
# ----------------------------------------------------------------------
# |
# |  Copyright David Brownell 2024
# |  Distributed under the MIT License.
# |
# ----------------------------------------------------------------------
"""\
Copies content to an offsite location: a snapshot is saved after the initial backup and
deltas are applied to that snapshot for subsequent backups.
"""

import datetime
import shutil

from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, cast, Iterator, Optional, Pattern

import typer

from dbrownell_Common import PathEx  # type: ignore[import-untyped]
from dbrownell_Common.Streams.DoneManager import DoneManager, Flags as DoneManagerFlags  # type: ignore[import-untyped]
from dbrownell_Common import TyperEx
from typer.core import TyperGroup

from FileBackup.CommandLine import CommandLineArguments
from FileBackup.Impl import Common
from FileBackup import Offsite


# ----------------------------------------------------------------------
class NaturalOrderGrouper(TyperGroup):
    # pylint: disable=missing-class-docstring
    # ----------------------------------------------------------------------
    def list_commands(self, *args, **kwargs):  # pylint: disable=unused-argument
        return self.commands.keys()  # pragma: no cover


# ----------------------------------------------------------------------
app = typer.Typer(
    cls=NaturalOrderGrouper,
    help=__doc__,
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
    pretty_exceptions_enable=False,
)


# ----------------------------------------------------------------------
_backup_name_argument = typer.Argument(
    ...,
    help="Unique name of the backup; this value allows for multiple distinct backups on the same machine.",
)
_destination_argument = typer.Argument(
    ...,
    help="Destination data store used to backup content; This value can be 'None' if the backup content should be created locally but manually distributed to the data store (this can be helpful when initially creating backups that are hundreds of GB in size). See the comments below for information on the different data store destination formats.",
)


# ----------------------------------------------------------------------
@app.command(
    "execute",
    epilog=Common.GetDestinationHelp(),
    no_args_is_help=True,
)
def Execute(
    backup_name: Annotated[str, _backup_name_argument],
    destination: Annotated[str, _destination_argument],
    input_filename_or_dirs: Annotated[
        list[Path],
        CommandLineArguments.input_filename_or_dirs_argument,
    ],
    encryption_password: Annotated[
        Optional[str],
        typer.Option(
            "--encryption-password",
            help="Encrypt the contents for backup prior to transferring them to the destination data store.",
        ),
    ] = None,
    compress: Annotated[
        bool,
        typer.Option(
            "--compress",
            help="Compress the contents to backup prior to transferring them to the destination data store.",
        ),
    ] = False,
    ssd: Annotated[bool, CommandLineArguments.ssd_option] = CommandLineArguments.ssd_option_default,
    force: Annotated[bool, CommandLineArguments.force_option] = CommandLineArguments.force_option_default,
    verbose: Annotated[
        bool, CommandLineArguments.verbose_option
    ] = CommandLineArguments.verbose_option_default,
    quiet: Annotated[bool, CommandLineArguments.quiet_option] = CommandLineArguments.quiet_option_default,
    debug: Annotated[bool, CommandLineArguments.debug_option] = CommandLineArguments.debug_option_default,
    working_dir: Annotated[
        Optional[Path],
        typer.Option(
            "--working-dir",
            file_okay=False,
            resolve_path=True,
            help="Local directory used to stage files prior to transferring them to the destination data store.",
        ),
    ] = None,
    archive_volume_size: Annotated[
        int,
        typer.Option(
            "--archive-volume-size",
            min=1024,
            help="Compressed/encrypted data will be converted to volumes of this size for easier transmission to the data store; value expressed in terms of bytes.",
        ),
    ] = Offsite.DEFAULT_ARCHIVE_VOLUME_SIZE,
    ignore_pending_snapshot: Annotated[
        bool,
        typer.Option("--ignore-pending-snapshot", help="Disable the pending warning snapshot and continue."),
    ] = False,
    file_include_params: Annotated[
        list[str],
        CommandLineArguments.file_include_option,
    ] = CommandLineArguments.file_include_option_default,
    file_exclude_params: Annotated[
        list[str],
        CommandLineArguments.file_exclude_option,
    ] = CommandLineArguments.file_exclude_option_default,
) -> None:
    """Prepares local changes for offsite backup."""

    file_includes = cast(list[Pattern], file_include_params)
    file_excludes = cast(list[Pattern], file_exclude_params)

    del file_include_params
    del file_exclude_params

    with DoneManager.CreateCommandLine(
        flags=DoneManagerFlags.Create(verbose=verbose, debug=debug),
    ) as dm:
        dm.WriteVerbose(str(datetime.datetime.now()) + "\n\n")

        destination_value = None if destination.lower() == "none" else destination

        with _ResolveWorkingDir(
            dm,
            working_dir,
            always_preserve=destination_value is None,
        ) as resolved_working_dir:
            Offsite.Backup(
                dm,
                backup_name,
                destination_value,
                input_filename_or_dirs,
                encryption_password,
                resolved_working_dir,
                compress=compress,
                ssd=ssd,
                force=force,
                quiet=quiet,
                file_includes=file_includes,
                file_excludes=file_excludes,
                archive_volume_size=archive_volume_size,
                ignore_pending_snapshot=ignore_pending_snapshot,
            )


# ----------------------------------------------------------------------
@app.command("commit", no_args_is_help=True)
def Commit(
    backup_name: Annotated[str, _backup_name_argument],
    verbose: Annotated[
        bool, CommandLineArguments.verbose_option
    ] = CommandLineArguments.verbose_option_default,
    debug: Annotated[bool, CommandLineArguments.debug_option] = CommandLineArguments.debug_option_default,
) -> None:
    """Commits a pending snapshot after the changes have been transferred to an offsite data store."""

    with DoneManager.CreateCommandLine(
        flags=DoneManagerFlags.Create(verbose=verbose, debug=debug),
    ) as dm:
        dm.WriteVerbose(str(datetime.datetime.now()) + "\n\n")

        Offsite.Commit(dm, backup_name)


# ----------------------------------------------------------------------
@app.command(
    "restore",
    epilog=Common.GetDestinationHelp(),
    no_args_is_help=True,
)
def Restore(  # pylint: disable=dangerous-default-value
    backup_name: Annotated[str, _backup_name_argument],
    backup_source: Annotated[
        str, typer.Argument(help="Data store location containing content that has been backed up.")
    ],
    encryption_password: Annotated[
        Optional[str],
        typer.Option(
            "--encryption-password",
            help="Password used when creating the backups.",
        ),
    ] = None,
    dir_substitution_key_value_args: Annotated[
        list[str],
        TyperEx.TyperDictOption(
            {},
            "--dir-substitution",
            allow_any__=True,
            help='A key-value-pair consisting of a string to replace and its replacement value within a posix string; this can be used when restoring to a location that is different from the location used to create the backup. Example: \'--dir-substitution "C\\:/=C\\:/Restore/" will cause files backed-up as "C:/Foo/Bar.txt" to be restored as "C:/Restore/Foo/Bar.txt". This value can be provided multiple times on the command line when supporting multiple substitutions.',
        ),
    ] = [],
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Show the changes that would be made during the restoration process, but do not modify the local file system.",
        ),
    ] = False,
    overwrite: Annotated[
        bool,
        typer.Option(
            "--overwrite",
            help="By default, the restoration process will not overwrite existing files on the local file system; this flag indicates that files should be overwritten as they are restored.",
        ),
    ] = False,
    ssd: Annotated[bool, CommandLineArguments.ssd_option] = CommandLineArguments.ssd_option_default,
    verbose: Annotated[
        bool, CommandLineArguments.verbose_option
    ] = CommandLineArguments.verbose_option_default,
    quiet: Annotated[bool, CommandLineArguments.quiet_option] = CommandLineArguments.quiet_option_default,
    debug: Annotated[bool, CommandLineArguments.debug_option] = CommandLineArguments.debug_option_default,
    working_dir: Annotated[
        Optional[Path],
        typer.Option(
            "--working-dir",
            file_okay=False,
            resolve_path=True,
            help="Working directory to use when decompressing archives; provide this value during a dry run and subsequent execution to only download and extract the backup content once.",
        ),
    ] = None,
    continue_on_errors: Annotated[
        bool,
        typer.Option(
            "--continue-on-errors", help="Continue restoring files even if some files cannot be restored."
        ),
    ] = False,
) -> None:
    """Restores content from an offsite data store."""

    with DoneManager.CreateCommandLine(
        flags=DoneManagerFlags.Create(verbose=verbose, debug=debug),
    ) as dm:
        dm.WriteVerbose(str(datetime.datetime.now()) + "\n\n")

        dir_substitutions = TyperEx.PostprocessDictArgument(dir_substitution_key_value_args)

        with _ResolveWorkingDir(dm, working_dir) as resolved_working_dir:
            Offsite.Restore(
                dm,
                backup_name,
                backup_source,
                encryption_password,
                resolved_working_dir,
                dir_substitutions,
                ssd=ssd,
                quiet=quiet,
                dry_run=dry_run,
                overwrite=overwrite,
                continue_on_errors=continue_on_errors,
            )


# ----------------------------------------------------------------------
# ----------------------------------------------------------------------
# ----------------------------------------------------------------------
@contextmanager
def _ResolveWorkingDir(
    dm: DoneManager,
    working_dir: Path | None,
    *,
    always_preserve: bool = False,
) -> Iterator[Path]:
    if working_dir is None:
        delete_dir = not always_preserve
        working_dir = PathEx.CreateTempDirectory()
    else:
        delete_dir = False

    was_successful = True

    try:
        assert working_dir is not None
        yield working_dir

    except:
        was_successful = False
        raise

    finally:
        assert working_dir is not None

        if delete_dir:
            was_successful = was_successful and dm.result == 0

            if was_successful:
                shutil.rmtree(working_dir)
            else:
                if dm.result <= 0:
                    # dm.result can be 0 if an exception was raised
                    type_desc = "errors"
                elif dm.result > 0:
                    type_desc = "warnings"
                else:
                    assert False, dm.result  # pragma: no cover

                dm.WriteInfo(f"The temporary directory '{working_dir}' was preserved due to {type_desc}.\n")


# ----------------------------------------------------------------------
# ----------------------------------------------------------------------
# ----------------------------------------------------------------------
if __name__ == "__main__":
    app()
