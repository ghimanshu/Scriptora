#!/bin/sh
set -eu
python -m ruff check app tests migrations
python -m ruff format --check app tests migrations
python -m mypy app
python -m pytest
python -m pip_audit -r requirements.lock
