#!/usr/bin/env sh
set -eu

python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
[ -f .env ] || cp .env.example .env
printf '%s\n' 'Setup completed. Fill .env and run ./run.sh.'
