# ----------------------------------------------------------------------
# |
# |  S3BrowserDataStore.py
# |
# |  David Brownell <db@DavidBrownell.com>
# |      2025-02-23 14:08:12
# |
# ----------------------------------------------------------------------
# |
# |  Copyright David Brownell 2025
# |  Distributed under the MIT License.
# |
# ----------------------------------------------------------------------
"""Contains the S3BrowserDataStore object"""

from pathlib import Path
from typing import Optional

from dbrownell_Common.Streams.DoneManager import DoneManager  # type: ignore[import-untyped]
from dbrownell_Common import SubprocessEx  # type: ignore[import-untyped]
from dbrownell_Common.Types import override  # type: ignore[import-untyped]

from FileBackup.DataStore.Interfaces.BulkStorageDataStore import BulkStorageDataStore


# ----------------------------------------------------------------------
class S3BrowserDataStore(BulkStorageDataStore):
    """Data store that uses the S3 Browser application (https://s3browser.com/)"""

    # ----------------------------------------------------------------------
    def __init__(
        self,
        account_name: str,
        bucket_name: str,
        s3_dir: Optional[Path],
    ) -> None:
        super(S3BrowserDataStore, self).__init__()

        self.account_name = account_name
        self.bucket_name = bucket_name

        self._s3_dir = self.bucket_name / (s3_dir or Path())

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
                "Validating S3 Browser on the command line...",
                suffix="\n",
            ) as check_dm:
                result = SubprocessEx.Run("s3browser-cli license show")

                check_dm.WriteVerbose(result.output)

                if result.returncode != 0:
                    check_dm.WriteError(
                        "S3 Browser is not available; please make sure it exists in the path and run the script again.\n"
                    )
                    return

                self._validated_command_line = True

        with dm.Nested("Uploading via S3 Browser...") as upload_dm:
            command_line = f's3browser-cli file upload "{self.account_name}" "{local_path / "*"}" "{self._s3_dir.as_posix()}"'

            upload_dm.WriteVerbose(f"Command Line: {command_line}\n\n")

            with upload_dm.YieldStream() as stream:
                upload_dm.result = SubprocessEx.Stream(command_line, stream)
