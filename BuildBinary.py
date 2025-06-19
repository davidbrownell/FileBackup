import os
import shutil

from pathlib import Path
from typing import Annotated, Optional

import typer

from dbrownell_Common import SubprocessEx
from dbrownell_Common.Streams.DoneManager import DoneManager, Flags as DoneManagerFlags
from typer.core import TyperGroup


# ----------------------------------------------------------------------
class NaturalOrderGrouper(TyperGroup):
    # pylint: disable=missing-class-docstring
    # ----------------------------------------------------------------------
    def list_commands(self, *args, **kwargs):  # pylint: disable=unused-argument
        return self.commands.keys()


# ----------------------------------------------------------------------
app = typer.Typer(
    cls=NaturalOrderGrouper,
    help=__doc__,
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
    pretty_exceptions_enable=False,
)


# ----------------------------------------------------------------------
@app.command("Build", no_args_is_help=False)
def Build(
    verbose: Annotated[
        bool,
        typer.Option("--verbose", help="Write verbose information to the terminal."),
    ] = False,
    debug: Annotated[
        bool,
        typer.Option("--debug", help="Write debug information to the terminal."),
    ] = False,
) -> None:
    """Build a standalone binary for the application."""

    with DoneManager.CreateCommandLine(
        flags=DoneManagerFlags.Create(verbose=verbose, debug=debug),
    ) as dm:
        command_line = "cxfreeze --script src/FileBackup/CommandLine/EntryPoint.py --target-name=FileBackup"

        dm.WriteVerbose(f"Command line: {command_line}\n\n")

        with dm.YieldStream() as stream:
            dm.result = SubprocessEx.Stream(command_line, stream)


# ----------------------------------------------------------------------
@app.command("Bundle", no_args_is_help=False)
def Bundle(
    custom_filename_suffix: Annotated[
        Optional[str],
        typer.Option("--custom-filename-suffix", help="Custom suffix for the output filename."),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", help="Write verbose information to the terminal."),
    ] = False,
    debug: Annotated[
        bool,
        typer.Option("--debug", help="Write debug information to the terminal."),
    ] = False,
) -> None:
    """Bundle a previously built standalone binary."""

    custom_filename_suffix = (custom_filename_suffix or "").removesuffix("-latest")

    with DoneManager.CreateCommandLine(
        flags=DoneManagerFlags.Create(verbose=verbose, debug=debug),
    ) as dm:
        build_dir = Path(__file__).parent / "build"

        if not build_dir.is_dir():
            dm.WriteError(
                f"The build directory '{build_dir}' does not exist. Please run the 'Build' command first.\n"
            )
            return

        subdirs = list(build_dir.iterdir())
        if len(subdirs) != 1 or not subdirs[0].is_dir():
            dm.WriteError(
                f"The build directory '{build_dir}' should contain exactly one subdirectory with the built binary and its dependencies.\n"
            )
            return

        build_dir /= subdirs[0]

        output_name = f"FileBackup{custom_filename_suffix or ''}"

        if os.name == "nt":
            output_filename = Path(f"{output_name}.zip")
            format = "zip"
        else:
            output_filename = Path(f"{output_name}.tar.gz")
            format = "gztar"

        with dm.Nested(f"Creating '{output_filename.name}'..."):
            output_filename.unlink(missing_ok=True)

            shutil.make_archive(
                output_name,
                format,
                root_dir=build_dir,
            )


# ----------------------------------------------------------------------
# ----------------------------------------------------------------------
# ----------------------------------------------------------------------
if __name__ == "__main__":
    app()
