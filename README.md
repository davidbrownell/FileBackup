# FileBackup

<!-- BEGIN: Exclude Package -->
[![License](https://img.shields.io/github/license/davidbrownell/FileBackup?color=dark-green)](https://github.com/davidbrownell/FileBackup/blob/master/LICENSE.txt)
[![GitHub commit activity](https://img.shields.io/github/commit-activity/y/davidbrownell/FileBackup?color=dark-green)](https://github.com/davidbrownell/FileBackup/commits/main/)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/FileBackup?color=dark-green)](https://pypi.org/project/FileBackup/)
[![PyPI - Version](https://img.shields.io/pypi/v/FileBackup?color=dark-green)](https://pypi.org/project/FileBackup/)
[![PyPI - Downloads](https://img.shields.io/pypi/dm/filebackup)](https://pypistats.org/packages/filebackup)
[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/9069/badge)](https://www.bestpractices.dev/projects/9069)
[![Code Coverage](https://img.shields.io/endpoint?url=https://gist.githubusercontent.com/davidbrownell/f15146b1b8fdc0a5d45ac0eb786a84f7/raw/FileBackup_coverage.json)](https://github.com/davidbrownell/FileBackup/actions)
<!-- END: Exclude Package -->

Tool for creating and restoring file system backups.

<!-- BEGIN: Exclude Package -->
## Contents
- [Overview](#overview)
- [Installation](#installation)
- [Development](#development)
- [Additional Information](#additional-information)
- [License](#license)
<!-- END: Exclude Package -->

## Overview
TODO: Complete this section

### How to use FileBackup
TODO: Complete this section

<!-- BEGIN: Exclude Package -->
## Installation
FileBackup can be installed via one of these methods:

- [Installation via Executable](#installation-via-executable)
- [Installation via pip](#installation-via-pip)

### Installation via Executable
Download an executable for Linux, MacOS, or Windows to the the functionality provided by this repository without a dependency on python.

1. Download the archive for the latest release [here](https://github.com/davidbrownell/FileBackup/releases/latest). The filename will begin with `exe.` and contain the name of your operating system.
2. Decompress the archive.

#### Verifying Signed Executables
Executables are signed and validated using [Minisign](https://jedisct1.github.io/minisign/). The public key used to verify the signature of the executable is `RWRGhtynC5g0o03VuBcJ3iIJoPgHATuMbAI2Weu7ST993WeK9BTv1B+C`.

To verify that the executable is valid, download the corresponding `.minisig` file [here](https://github.com/davidbrownell/FileBackup/releases/latest) and run this command, replacing `<filename>` with the name of the file to be verified:

`docker run -i --rm -v .:/host jedisct1/minisign -V -P RWRGhtynC5g0o03VuBcJ3iIJoPgHATuMbAI2Weu7ST993WeK9BTv1B+C -m /host/<filename>`

Instructions for installing [docker](https://docker.com) are available at https://docs.docker.com/engine/install/.

### Installation via pip
To install the FileBackup package via [pip](https://pip.pypa.io/en/stable/) (Python Installer for Python) for use with your python code:

`pip install FileBackup`


## Development
Please visit [Contributing](https://github.com/davidbrownell/FileBackup/blob/main/CONTRIBUTING.md) and [Development](https://github.com/davidbrownell/FileBackup/blob/main/DEVELOPMENT.md) for information on contributing to this project.
<!-- END: Exclude Package -->

## Additional Information
Additional information can be found at these locations.

| Title | Document | Description |
| --- | --- | --- |
| Code of Conduct | [CODE_OF_CONDUCT.md](https://github.com/davidbrownell/FileBackup/blob/main/CODE_OF_CONDUCT.md) | Information about the the norms, rules, and responsibilities we adhere to when participating in this open source community. |
| Contributing | [CONTRIBUTING.md](https://github.com/davidbrownell/FileBackup/blob/main/CONTRIBUTING.md) | Information about contributing code changes to this project. |
| Development | [DEVELOPMENT.md](https://github.com/davidbrownell/FileBackup/blob/main/DEVELOPMENT.md) | Information about development activities involved in making changes to this project. |
| Governance | [GOVERNANCE.md](https://github.com/davidbrownell/FileBackup/blob/main/GOVERNANCE.md) | Information about how this project is governed. |
| Maintainers | [MAINTAINERS.md](https://github.com/davidbrownell/FileBackup/blob/main/MAINTAINERS.md) | Information about individuals who maintain this project. |
| Security | [SECURITY.md](https://github.com/davidbrownell/FileBackup/blob/main/SECURITY.md) | Information about how to privately report security issues associated with this project. |

## License

FileBackup is licensed under the <a href="https://choosealicense.com/licenses/mit/" target="_blank">MIT</a> license.
