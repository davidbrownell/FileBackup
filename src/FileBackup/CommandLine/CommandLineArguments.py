# ----------------------------------------------------------------------
# |
# |  CommandLineArguments.py
# |
# |  David Brownell <db@DavidBrownell.com>
# |      2024-06-12 13:20:05
# |
# ----------------------------------------------------------------------
# |
# |  Copyright David Brownell 2024
# |  Distributed under the MIT License.
# |
# ----------------------------------------------------------------------

import re

from typing import Pattern

import typer


# ----------------------------------------------------------------------
def ToRegex(
    values: list[str],
) -> list[Pattern]:
    expressions: list[Pattern] = []

    for value in values:
        try:
            expressions.append(re.compile("^{}$".format(value)))
        except re.error as ex:
            raise typer.BadParameter("The regular expression '{}' is not valid ({}).".format(value, ex))

    return expressions


# ----------------------------------------------------------------------
input_filename_or_dirs_argument = typer.Argument(
    ..., exists=True, resolve_path=True, help="Input filename or directory."
)

ssd_option = typer.Option(
    "--ssd",
    help="Processes tasks in parallel to leverage the capabilities of solid-state-drives.",
)
ssd_option_default = False

quiet_option = typer.Option("--quiet", help="Reduce the amount of information displayed.")
quiet_option_default = False

force_option = typer.Option(
    "--force",
    help="Ignore previous backup information and overwrite all data in the destination data store.",
)
force_option_default = False

verbose_option = typer.Option("--verbose", help="Write verbose information to the terminal.")
verbose_option_default = False

debug_option = typer.Option("--debug", help="Write debug information to the terminal.")
debug_option_default = False

file_include_option = typer.Option(
    "--file-include",
    callback=ToRegex,
    help="Regular expression (based on a posix path) used to include files and/or directories when preserving content.",
)
file_include_option_default: list[str] = []

file_exclude_option = typer.Option(
    "--file-exclude",
    callback=ToRegex,
    help="Regular expression (based on a posix path) used to exclude files and/or directories when preserving content.",
)
file_exclude_option_default: list[str] = []
