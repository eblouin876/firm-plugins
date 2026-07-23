#!/usr/bin/env python
"""Django's management entrypoint. Not a vendored file — standard Django
project boilerplate (`django-admin startproject` output), pointed at
`config.settings`. `DJANGO_SETTINGS_MODULE` can be overridden via env (e.g.
`config.settings_test` for the hermetic sqlite settings — see
`config/settings_test.py` and this block's README, "Testing")."""
import os
import sys


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment? (`uv sync`, then "
            "`uv run python manage.py ...`)"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
