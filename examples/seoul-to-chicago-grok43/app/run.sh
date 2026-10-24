#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  uv venv --python 3.11 .venv
fi
VIRTUAL_ENV="$PWD/.venv" uv pip install -r requirements.txt

if [ -f .env ]; then
  set -a; source .env; set +a
else
  echo ".env 파일이 없습니다. cp .env.example .env 후 값을 채우세요." >&2
fi

exec .venv/bin/uvicorn server:app --host 127.0.0.1 --port 8765 --reload
