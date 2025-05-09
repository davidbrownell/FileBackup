**Project:**
[![License](https://img.shields.io/github/license/davidbrownell/FileBackup?color=dark-green)](https://github.com/davidbrownell/FileBackup/blob/master/LICENSE)

**Package:**
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/FileBackup?color=dark-green)](https://pypi.org/project/FileBackup/)
[![PyPI - Version](https://img.shields.io/pypi/v/FileBackup?color=dark-green)](https://pypi.org/project/FileBackup/)
[![PyPI - Downloads](https://img.shields.io/pypi/dm/FileBackup)](https://pypistats.org/packages/FileBackup)

**Development:**
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![CI](https://github.com/davidbrownell/FileBackup/actions/workflows/CICD.yml/badge.svg)](https://github.com/davidbrownell/FileBackup/actions/workflows/CICD.yml)
[![Code Coverage](https://img.shields.io/endpoint?url=https://gist.githubusercontent.com/davidbrownell/f15146b1b8fdc0a5d45ac0eb786a84f7/raw/FileBackup_code_coverage.json)](https://github.com/davidbrownell/FileBackup/actions)
[![GitHub commit activity](https://img.shields.io/github/commit-activity/y/davidbrownell/FileBackup?color=dark-green)](https://github.com/davidbrownell/FileBackup/commits/main/)

<!-- Content above this delimiter will be copied to the generated README.md file. DO NOT REMOVE THIS COMMENT, as it will cause regeneration to fail. -->

## Contents
- [Overview](#overview)
- [Installation](#installation)
- [Development](#development)
- [Additional Information](#additional-information)
- [License](#license)

## Overview
TODO: Complete this section

### How to use FileBackup
TODO: Complete this section

<!-- Content below this delimiter will be copied to the generated README.md file. DO NOT REMOVE THIS COMMENT, as it will cause regeneration to fail. -->

## Installation

| Installation Method | Command |
| --- | --- |
| Via [uv](https://github.com/astral-sh/uv) | `uv add FileBackup` |
| Via [pip](https://pip.pypa.io/en/stable/) | `pip install FileBackup` |

### Verifying Signed Artifacts
Artifacts are signed and validated using [py-minisign](https://github.com/x13a/py-minisign) and the public key in the file `./minisign_key.pub`.

To verify that an artifact is valid, visit [the latest release](https://github.com/davidbrownell/FileBackup/releases/latest) and download the `.minisign` signature file that corresponds to the artifact, then run the following command, replacing `<filename>` with the name of the artifact to be verified:

`uv run --with py-minisign python -c "import minisign; minisign.PublicKey.from_file('minisign_key.pub').verify_file('<filename>')"`

## Development
Please visit [Contributing](https://github.com/davidbrownell/FileBackup/blob/main/CONTRIBUTING.md) and [Development](https://github.com/davidbrownell/FileBackup/blob/main/DEVELOPMENT.md) for information on contributing to this project.

## Additional Information
Additional information can be found at these locations.

| Title | Document | Description |
| --- | --- | --- |
| Code of Conduct | [CODE_OF_CONDUCT.md](https://github.com/davidbrownell/FileBackup/blob/main/CODE_OF_CONDUCT.md) | Information about the norms, rules, and responsibilities we adhere to when participating in this open source community. |
| Contributing | [CONTRIBUTING.md](https://github.com/davidbrownell/FileBackup/blob/main/CONTRIBUTING.md) | Information about contributing to this project. |
| Development | [DEVELOPMENT.md](https://github.com/davidbrownell/FileBackup/blob/main/DEVELOPMENT.md) | Information about development activities involved in making changes to this project. |
| Governance | [GOVERNANCE.md](https://github.com/davidbrownell/FileBackup/blob/main/GOVERNANCE.md) | Information about how this project is governed. |
| Maintainers | [MAINTAINERS.md](https://github.com/davidbrownell/FileBackup/blob/main/MAINTAINERS.md) | Information about individuals who maintain this project. |
| Security | [SECURITY.md](https://github.com/davidbrownell/FileBackup/blob/main/SECURITY.md) | Information about how to privately report security issues associated with this project. |

## License
FileBackup is licensed under the <a href="https://choosealicense.com/licenses/MIT/" target="_blank">MIT</a> license.
