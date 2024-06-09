# FileBackup

<!-- BEGIN: Exclude Package -->
[![CI](https://github.com/davidbrownell/FileBackup/actions/workflows/standard.yaml/badge.svg?event=push)](https://github.com/davidbrownell/FileBackup/actions/workflows/standard.yaml)
[![Code Coverage](https://img.shields.io/endpoint?url=https://gist.githubusercontent.com/davidbrownell/f15146b1b8fdc0a5d45ac0eb786a84f7/raw/FileBackup_coverage.json)](https://github.com/davidbrownell/FileBackup/actions)
[![License](https://img.shields.io/github/license/davidbrownell/FileBackup?color=dark-green)](https://github.com/davidbrownell/FileBackup/blob/master/LICENSE.txt)
[![GitHub commit activity](https://img.shields.io/github/commit-activity/y/davidbrownell/FileBackup?color=dark-green)](https://github.com/davidbrownell/FileBackup/commits/main/)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/FileBackup?color=dark-green)](https://pypi.org/project/filebackup/)
[![PyPI - Version](https://img.shields.io/pypi/v/FileBackup?color=dark-green)](https://pypi.org/project/filebackup/)
[![PyPI - Downloads](https://img.shields.io/pypi/dm/FileBackup)](https://pypistats.org/packages/filebackup)
[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/9069/badge)](https://www.bestpractices.dev/projects/9069)

<!-- END: Exclude Package -->

Tool for creating and restoring file system backups.

<!-- BEGIN: Exclude Package -->
## Contents
- [Overview](#overview)
- [Installation](#installation)
- [Contributing](#contributing)
- [Local Development](#local-development)
- [Vulnerability Reporting](#vulnerability-reporting-security-issues)
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

Download an executable for Linux, MacOS, or Windows to use the functionality provided by this repository without a dependency on [Python](https://www.python.org).

1. Download the archive for the latest release [here](https://github.com/davidbrownell/FileBackup/releases/latest); the files will begin with `exe.` and contain the name of your operating system.
2. Decompress the archive


#### Verifying Signed Executables

Executables are signed and validated using [Minisign](https://jedisct1.github.io/minisign/).

The public key for executables in this repository is `RWTO8gifpEKQhwiguxsldM47Php1GeTs0foueIpaLPp0xSy0N5FBn/70`.

To verify that the executable is valid, download the corresponding `.minisig` file [here](https://github.com/davidbrownell/FileBackup/releases/latest) and run this command, replacing `<filename>` with the name of your file.

`docker run -i --rm -v .:/host jedisct1/minisign -V -P RWTO8gifpEKQhwiguxsldM47Php1GeTs0foueIpaLPp0xSy0N5FBn/70 -m /host/<filename>`

Instructions for installing [docker](https://docker.com) are available at https://docs.docker.com/engine/install/.



### Installation via pip

Install the FileBackup package via [pip](https://pip.pypa.io/en/stable/) (Package Installer for Python) to use it with your python code.

`pip install FileBackup`

## Contributing
See [CONTRIBUTING.md](https://github.com/davidbrownell/FileBackup/blob/main/CONTRIBUTING.md) for information on contributing to FileBackup.

## Local Development

See [DEVELOPMENT.md](https://github.com/davidbrownell/FileBackup/blob/main/DEVELOPMENT.md) for information on developing or testing FileBackup on your local Linux, MacOS, or Windows machine.
<!-- END: Exclude Package -->

## Vulnerability Reporting (Security Issues)
Please privately report vulnerabilities you find so we can fix them!

See [SECURITY.md](https://github.com/davidbrownell/FileBackup/blob/main/SECURITY.md) for information on how to privately report vulnerabilities.

## License

FileBackup is licensed under the <a href="https://choosealicense.com/licenses/mit/" target="_blank">MIT</a> license.
