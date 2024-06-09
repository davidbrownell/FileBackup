# Contributing

Feedback and contributions are very welcome!

Here's help on how to make contributions, divided into the following sections:

- [general information](#general-information),
- [vulnerability reporting](#vulnerability-reporting-security-issues),
- [code changes](#code-changes),

## General information
For specific proposals, please provide them as [pull requests](https://github.com/coreinfrastructure/best-practices-badge/pulls) or [issues](https://github.com/coreinfrastructure/best-practices-badge/issues) via our [GitHub site](https://github.com/davidbrownell/FileBackup).

The [DEVELOPMENT.md](https://github.com/davidbrownell/FileBackup/blob/main/DEVELOPMENT.md) file explains how to install the program locally (highly recommended if you're going to make code changes). It also provides a quick start guide.

### Pull requests and different branches recommended
Pull requests are preferred, since they are specific. For more about how to create a pull request, see https://help.github.com/articles/using-pull-requests/.

We recommend creating different branches for different (logical) changes, and creating a pull request when you're done into the main branch. See the GitHub documentation on [creating branches](https://help.github.com/articles/creating-and-deleting-branches-within-your-repository/) and [using pull requests](https://help.github.com/articles/using-pull-requests/).

### How we handle proposals
We use GitHub to track proposed changes via its [issue tracker](https://github.com/coreinfrastructure/best-practices-badge/issues) and [pull requests](https://github.com/coreinfrastructure/best-practices-badge/pulls). Specific changes are proposed using those mechanisms. Issues are assigned to an individual, who works and then marks it complete. If there are questions or objections, the conversation are of that issue or pull request is used to resolve it.

### We are proactive
In general we try to be proactive to detect and eliminate mistakes and vulnerabilities as soon as possible, and to reduce their impact when they do happen. We use a defensive design and coding style to reduce the likelihood of mistakes, a variety of tools that try to detect mistakes early, and an automatic test suite with significant coverage. We also release the software as open source software so others can review it.

Since early detection and impact reduction can never be perfect, we also try to detect and repair problems during deployment as quickly as possible. This is especially true for security issues; see our [security information](#vulnerability-reporting-security-issues) for more.

## Vulnerability reporting (security issues)
Please privately report vulnerabilities you find so we can fix them!

See [SECURITY.md](https://github.com/davidbrownell/FileBackup/blob/main/SECURITY.md) for information on how to privately report vulnerabilities.

## Code changes
To make changes to the "FileBackup" web application that implements the criteria, you may find [DEVELOPMENT.md](https://github.com/davidbrownell/FileBackup/blob/main/DEVELOPMENT.md) helpful.

The code should strive to be DRY (don't repeat yourself), clear, and obviously correct. Some technical debt is inevitable, just don't bankrupt us with it. Improved refactorizations are welcome.

### Automated tests
When adding or changing functionality, please include new tests for them as part of your contribution.

We require the code to have at a minimum statement coverage (that is measured and enforced during the [Continuous Integration](https://en.wikipedia.org/wiki/Continuous_integration) process); please ensure your contributions do not lower the coverage below that minimum.

We encourage tests to be created first, run to ensure they fail, and then add code to implement the test (aka test driven development). However, each git commit should have both the test and improvement in the same commit, because 'git bisect' will then work well.

### How to check proposed changes before submitting them
See [DEVELOPMENT.md](https://github.com/davidbrownell/FileBackup/blob/main/DEVELOPMENT.md) for information on how to run tests on your local machine before submitting them as a pull request.

### Git commit messages
When writing git commit messages, try to follow the guidelines in [How to Write a Git Commit Message](https://chris.beams.io/posts/git-commit/):

1. Separate subject from body with a blank line
2. Limit the subject line to 50 characters. (We're flexible on this, but do limit it to 72 characters or less.)
3. Capitalize the subject line
4. Do not end the subject line with a period
5. Use the imperative mood in the subject line (command form)
6. Wrap the body at 72 characters ("fmt -w 72")
7. Use the body to explain what and why vs. how (git tracks how it was changed in detail, don't repeat that)
