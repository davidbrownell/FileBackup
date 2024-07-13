# ----------------------------------------------------------------------
# |
# |  Copyright (c) 2024 David Brownell
# |  Distributed under the MIT License.
# |
# ----------------------------------------------------------------------
"""Tools to backup and restore files and directories."""

import sys

import typer

from typer.core import TyperGroup  # type: ignore [import-untyped]

from FileBackup import __version__
from FileBackup.CommandLine import MirrorEntryPoint
from FileBackup.CommandLine import OffsiteEntryPoint


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


app.add_typer(MirrorEntryPoint.app, name="mirror", help=MirrorEntryPoint.__doc__)
app.add_typer(OffsiteEntryPoint.app, name="offsite", help=OffsiteEntryPoint.__doc__)


@app.command("version", no_args_is_help=False)
def Version():
    """Displays the current version and exits."""

    sys.stdout.write(f"FileBackup v{__version__}\n")


# ----------------------------------------------------------------------
# ----------------------------------------------------------------------
# ----------------------------------------------------------------------
if __name__ == "__main__":
    app()  # pragma: no cover
