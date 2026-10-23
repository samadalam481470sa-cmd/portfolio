#!/bin/bash
# Double-click this file on a Mac to start the Wholesale Hub.
# The first run builds a private Python environment and installs the packages.
cd "$(dirname "$0")" || exit 1

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is not installed. Install it from python.org, then run this again."
  read -r -p "Press Return to close."
  exit 1
fi
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)'; then
  echo "Python 3.9 or newer is needed. Install the latest Python from python.org."
  read -r -p "Press Return to close."
  exit 1
fi

if [ ! -d .venv ]; then
  echo "First run: setting up. This takes a minute."
  python3 -m venv .venv || exit 1
fi
.venv/bin/pip install -q --disable-pip-version-check -r requirements.txt || exit 1

PORT=$(.venv/bin/python -c "from hub.config import CONFIG; print(CONFIG['port'])")
HOST=$(.venv/bin/python -c "from hub.config import CONFIG; print(CONFIG['host'])")

# Open the dashboard once the server is up.
( sleep 3; open "http://${HOST}:${PORT}" ) &

echo "Wholesale Hub is starting at http://${HOST}:${PORT}"
echo "Close this window or press Control-C to stop it."

# caffeinate keeps the Mac from sleeping while the hub runs (system sleep is blocked on power).
if command -v caffeinate >/dev/null 2>&1; then
  exec caffeinate -is .venv/bin/python run.py
else
  exec .venv/bin/python run.py
fi
