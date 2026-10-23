#!/bin/sh
# One-time setup on a new Mac: creates the virtual environment and installs dependencies.
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
PY="${PYTHON:-python3}"
"$PY" -c 'import sys; assert sys.version_info >= (3, 10), "Python 3.10+ required"'
[ -d "$DIR/.venv" ] || "$PY" -m venv "$DIR/.venv"
"$DIR/.venv/bin/pip" install -q --upgrade pip
"$DIR/.venv/bin/pip" install -q -r "$DIR/requirements.txt"
chmod +x "$DIR/hg" "$DIR/service.sh"
"$DIR/.venv/bin/python" -c "import torch; print('PyTorch', torch.__version__, '| Apple GPU (MPS):', torch.backends.mps.is_available())"
echo "Installed. Next: ./hg setup --folders ~/Documents ~/Desktop && ./hg pipeline"
