import os
import shutil
import textwrap
import uuid

from importlib import metadata
from pathlib import Path
from typing import Annotated, Optional

import typer

from dbrownell_Common.ContextlibEx import ExitStack
from dbrownell_Common import SubprocessEx
from dbrownell_Common.Streams.DoneManager import DoneManager, Flags as DoneManagerFlags
import inflect
from typer.core import TyperGroup

import FileBackup


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
        # inflect uses the typeguard library, which relies on inspect to read the source code of
        # inflect to enforce that arguments are the correct types when invoking functions. This
        # works fine when running the application normally, but does not work by default with
        # cx_Freeze because it does not include the source code of inflect in the built binary. This
        # means that typeguard can't determine the types of the arguments, which causes it to raise
        # an exception. The fix is to include the inflect source code in the built binary so that
        # typeguard can find the function's types and not raise an exception.
        #
        # Note that this must be an absolute path; inflect is installed into the virtual
        # environment, which is not guaranteed to live under this file's directory (for example,
        # when UV_PROJECT_ENVIRONMENT points elsewhere).
        inflect_filename = Path(inflect.__file__).resolve()

        # FileBackup/__init__.py invokes importlib.metadata.version to determine the version of the
        # application, which requires that this distribution's metadata is included in the binary.
        #
        # cx_Freeze automatically includes the metadata of the distributions that it detects, but it
        # does not reliably detect this one. cx_Freeze (>= 8.7.0) maps import names to distributions
        # using importlib.metadata.packages_distributions, and that function cannot map the
        # "FileBackup" import name back to the "FileBackup" distribution because the distribution is
        # installed in editable mode (its top_level.txt is empty and the package is made available
        # via a .pth file). cx_Freeze then falls back to including any distribution that it did not
        # map, which happens to work on a development machine but not on a build machine.
        #
        # Without this metadata, the binary terminates during startup with
        # "importlib.metadata.PackageNotFoundError: No package metadata was found for FileBackup".
        #
        # Include the metadata explicitly so that it is found at runtime regardless of the above.
        distribution = metadata.distribution("FileBackup")

        dist_info_path = Path(str(distribution.locate_file(""))).resolve() / "{}-{}.dist-info".format(
            distribution.name.replace("-", "_").lower(),
            distribution.version,
        )

        if not dist_info_path.is_dir():
            dm.WriteError(f"The distribution metadata at '{dist_info_path}' was not found.\n")
            return

        # Note that this is written as a single line so that it does not interfere with the
        # textwrap.dedent invocation below.
        zip_includes = ", ".join(
            '(r"{}", "{}/{}")'.format(
                filename,
                dist_info_path.name,
                filename.relative_to(dist_info_path).as_posix(),
            )
            for filename in sorted(dist_info_path.rglob("*"))
            if filename.is_file()
        )

        configuration_filename = Path("setup{}.py".format(str(uuid.uuid4()).replace("-", "")))

        configuration_filename.write_text(
            textwrap.dedent(
                f"""\
                from cx_Freeze import setup, Executable

                setup(
                    name = "FileBackup",
                    version = "{FileBackup.__version__}",
                    options = {{
                        "build_exe": {{
                        "include_files": [
                            (r"{inflect_filename}", "lib/inflect/{inflect_filename.name}"),
                        ],
                        # This distribution's metadata is placed within the zip file because that is
                        # where importlib.metadata looks for it at runtime.
                        "zip_includes": [{zip_includes}],
                        # typeguard (pulled in by inflect) imports unittest.mock at module scope,
                        # but cx_Freeze does not detect unittest as a dependency. Without it, the
                        # binary fails at startup with "No module named 'unittest'".
                        "packages": ["unittest"],
                        }},
                    }},
                    executables = [
                        Executable(
                            "src/FileBackup/CommandLine/EntryPoint.py",
                            target_name="FileBackup",
                            base=None,
                        ),
                    ],
                )
                """,
            ),
            encoding="utf-8",
        )

        with ExitStack(configuration_filename.unlink):
            with dm.YieldStream() as stream:
                dm.result = SubprocessEx.Stream(f'python "{configuration_filename}" build_exe', stream)


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
