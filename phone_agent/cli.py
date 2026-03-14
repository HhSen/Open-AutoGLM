"""Entry point for the phone-use CLI command.

This module is registered as the console_scripts entry point so that
`phone-use` works from anywhere on the system, regardless of the working
directory.  It patches sys.path to include the repository root (where
main.py lives) before importing, then hands off to main().
"""

import os
import sys


def main() -> None:
    # Ensure the repository root (the directory that contains main.py) is on
    # sys.path so `import main` succeeds no matter where the command is run.
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    from main import main as _main  # noqa: PLC0415

    _main()
