# ----------------------------------------------------------------------
# |
# |  MirrorEntryPoint.py
# |
# |  David Brownell <db@DavidBrownell.com>
# |      2024-06-12 13:16:52
# |
# ----------------------------------------------------------------------
# |
# |  Copyright David Brownell 2024
# |  Distributed under the MIT License.
# |
# ----------------------------------------------------------------------
"""\
Mirrors backup content: files created locally will be added to the backup data store; files deleted
locally will be removed from the backup data store; files modified locally will be modified at the
backup data store.
"""

import datetime
import textwrap

from pathlib import Path
from typing import Annotated, cast, Pattern

import typer

from dbrownell_Common.Streams.DoneManager import DoneManager, Flags as DoneManagerFlags  # type: ignore [import-untyped]
from typer.core import TyperGroup  # type: ignore [import-untyped]

from FileBackup.CommandLine import CommandLineArguments
from FileBackup.Impl import Common
from FileBackup import Mirror


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
_destination_argument = typer.Argument(
    ...,
    help="Destination data store used when mirroring local content; see the comments below for information on the different data store destination formats.",
)


# ----------------------------------------------------------------------
@app.command(
    "execute",
    epilog=Common.GetDestinationHelp(),
    no_args_is_help=True,
)
def Execute(
    destination: Annotated[str, _destination_argument],
    input_filename_or_dirs: Annotated[
        list[Path],
        CommandLineArguments.input_filename_or_dirs_argument,
    ],
    ssd: Annotated[bool, CommandLineArguments.ssd_option] = CommandLineArguments.ssd_option_default,
    force: Annotated[bool, CommandLineArguments.force_option] = CommandLineArguments.force_option_default,
    verbose: Annotated[
        bool, CommandLineArguments.verbose_option
    ] = CommandLineArguments.verbose_option_default,
    quiet: Annotated[bool, CommandLineArguments.quiet_option] = CommandLineArguments.quiet_option_default,
    debug: Annotated[bool, CommandLineArguments.debug_option] = CommandLineArguments.debug_option_default,
    file_include_params: Annotated[
        list[str],
        CommandLineArguments.file_include_option,
    ] = CommandLineArguments.file_include_option_default,
    file_exclude_params: Annotated[
        list[str],
        CommandLineArguments.file_exclude_option,
    ] = CommandLineArguments.file_exclude_option_default,
) -> None:
    """Mirrors content to a backup data store."""

    file_includes = cast(list[Pattern], file_include_params)
    file_excludes = cast(list[Pattern], file_exclude_params)

    del file_include_params
    del file_exclude_params

    with DoneManager.CreateCommandLine(
        flags=DoneManagerFlags.Create(verbose=verbose, debug=debug),
    ) as dm:
        dm.WriteVerbose(str(datetime.datetime.now()) + "\n\n")

        Mirror.Backup(
            dm,
            destination,
            input_filename_or_dirs,
            ssd=ssd,
            force=force,
            quiet=quiet,
            file_includes=file_includes,
            file_excludes=file_excludes,
        )


# ----------------------------------------------------------------------
@app.command(
    "validate",
    no_args_is_help=True,
    epilog=textwrap.dedent(
        """\
        {}
        Validation Types
        ================
            standard: Validates that files and directories at the destination exist and file sizes match the expected values.
            complete: Validates that files and directories at the destination exist and file hashes match the expected values.
        """,
    )
    .replace("\n", "\n\n")
    .format(Common.GetDestinationHelp()),
)
def Validate(
    destination: Annotated[str, _destination_argument],
    validate_type: Annotated[
        Mirror.ValidateType,
        typer.Argument(
            case_sensitive=False,
            help="Specifies the type of validation to use; the the comments below for information on the different validation types.",
        ),
    ] = Mirror.ValidateType.standard,
    ssd: Annotated[bool, CommandLineArguments.ssd_option] = CommandLineArguments.ssd_option_default,
    verbose: Annotated[
        bool, CommandLineArguments.verbose_option
    ] = CommandLineArguments.verbose_option_default,
    quiet: Annotated[bool, CommandLineArguments.quiet_option] = CommandLineArguments.quiet_option_default,
    debug: Annotated[bool, CommandLineArguments.debug_option] = CommandLineArguments.debug_option_default,
) -> None:
    """Validates previously mirrored content in the backup data store."""

    with DoneManager.CreateCommandLine(
        flags=DoneManagerFlags.Create(verbose=verbose, debug=debug),
    ) as dm:
        dm.WriteVerbose(str(datetime.datetime.now()) + "\n\n")

        Mirror.Validate(
            dm,
            destination,
            validate_type,
            ssd=ssd,
            quiet=quiet,
        )


# ----------------------------------------------------------------------
@app.command(
    "cleanup",
    epilog=Common.GetDestinationHelp(),
    no_args_is_help=True,
)
def Cleanup(
    destination: Annotated[str, _destination_argument],
    verbose: Annotated[
        bool, CommandLineArguments.verbose_option
    ] = CommandLineArguments.verbose_option_default,
    debug: Annotated[bool, CommandLineArguments.debug_option] = CommandLineArguments.debug_option_default,
) -> None:
    """Cleans a backup data store after a mirror execution that was interrupted or failed."""

    with DoneManager.CreateCommandLine(
        flags=DoneManagerFlags.Create(verbose=verbose, debug=debug),
    ) as dm:
        dm.WriteVerbose(str(datetime.datetime.now()) + "\n\n")

        Mirror.Cleanup(dm, destination)
