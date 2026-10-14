"""python -m clickwheel"""

import sys

try:
    from .cli import main
except ModuleNotFoundError as exc:  # usually: a Python without the project's .venv
    sys.exit(
        f"Clickwheel needs the '{exc.name}' package, which this Python ({sys.executable}) does not have.\n"
        "Run it through ./run.sh, which uses the project's .venv:\n"
        "    ./run.sh                  start the app\n"
    )

if __name__ == "__main__":
    sys.exit(main())
