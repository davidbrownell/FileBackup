# ----------------------------------------------------------------------
# |
# |  FastGlacierDataStore.py
# |
# |  David Brownell <db@DavidBrownell.com>
# |      2024-06-10 14:32:10
# |
# ----------------------------------------------------------------------
# |
# |  Copyright David Brownell 2024
# |  Distributed under the MIT License.
# |
# ----------------------------------------------------------------------
"""Contains the FastGlacierDataStore object"""

from pathlib import Path
from typing import Optional

from dbrownell_Common.Streams.DoneManager import DoneManager  # type: ignore[import-untyped]
from dbrownell_Common import SubprocessEx  # type: ignore[import-untyped]
from dbrownell_Common.Types import override  # type: ignore[import-untyped]

from FileBackup.DataStore.Interfaces.BulkStorageDataStore import BulkStorageDataStore


# ----------------------------------------------------------------------
class FastGlacierDataStore(BulkStorageDataStore):
    """Data store that uses the Fast Glacier application (https://fastglacier.com/)"""

    # ----------------------------------------------------------------------
    def __init__(
        self,
        account_name: str,
        aws_region: str,
        glacier_dir: Optional[Path],
    ):
        super(FastGlacierDataStore, self).__init__()

        self.account_name = account_name
        self.aws_region = aws_region

        self._glacier_dir = glacier_dir or Path()

        self._validated_command_line = False

    # ----------------------------------------------------------------------
    @override
    def ExecuteInParallel(self) -> bool:
        return False

    # ----------------------------------------------------------------------
    @override
    def Upload(
        self,
        dm: DoneManager,
        local_path: Path,
    ) -> None:
        if self._validated_command_line is False:
            with dm.Nested(
                "Validating Fast Glacier on the command line...",
                suffix="\n",
            ) as check_dm:
                result = SubprocessEx.Run("glacier-con --version")

                check_dm.WriteVerbose(result.output)

                if result.returncode != 0 and "glacier-con.exe upload" not in result.output:
                    check_dm.WriteError(
                        "Fast Glacier is not available; please make sure it exists in the path and run the script again.\n"
                    )
                    return

            with dm.Nested("Uploading to Fast Glacier...") as upload_dm:
                command_line = f'glacier-con upload "{self.account_name}" "{local_path / "*"}" "{self.aws_region}" "{self._glacier_dir.as_posix()}"'

                upload_dm.WriteVerbose(f"Command Line: {command_line}\n\n")

                with upload_dm.YieldStream() as stream:
                    upload_dm.result = SubprocessEx.Stream(command_line, stream)
