#!/bin/bash
set -Eeuo pipefail

cd "$(dirname "$0")"
export PYTHONUTF8=1
trap 'status=$?; echo "[ERROR] Startup stopped (exit $status). Review the message above." >&2' ERR

fail() {
  echo "[ERROR] $1" >&2
  exit 1
}

valid_python() {
  "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1
}

find_python() {
  local candidate
  for candidate in \
    /opt/homebrew/opt/python@3.11/bin/python3.11 \
    /usr/local/opt/python@3.11/bin/python3.11 \
    python3.11 python3.12 python3; do
    if command -v "$candidate" >/dev/null 2>&1 && valid_python "$candidate"; then
      command -v "$candidate"
      return 0
    fi
  done
  return 1
}

find_brew() {
  local candidate
  for candidate in /opt/homebrew/bin/brew /usr/local/bin/brew brew; do
    if command -v "$candidate" >/dev/null 2>&1; then
      command -v "$candidate"
      return 0
    fi
  done
  return 1
}

install_homebrew() {
  command -v curl >/dev/null 2>&1 || fail 'Python and Homebrew are missing, and curl is unavailable. Install Python 3.11 from https://www.python.org/downloads/macos/'
  local installer
  installer="$(mktemp "${TMPDIR:-/tmp}/rag-homebrew.XXXXXX")"
  echo 'Python and Homebrew are missing. Downloading the official Homebrew installer...'
  if ! curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh -o "$installer"; then
    rm -f "$installer"
    fail 'Homebrew installer download failed. Check the network and try again.'
  fi
  if ! /bin/bash "$installer"; then
    rm -f "$installer"
    fail 'Homebrew installation failed. Check the installer output above.'
  fi
  rm -f "$installer"
  export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
}

check_project_imports() {
  "$1" -c 'import fastapi, uvicorn, numpy, sklearn, pypdf; import importlib.metadata as m; m.version("python-multipart")' >/dev/null 2>&1
}

venv_python='.venv/bin/python'
echo '[1/5] Checking Python 3.9 or newer...'
if valid_python "$venv_python"; then
  echo 'Using the existing project virtual environment.'
else
  python_bin="$(find_python || true)"
  if [ -z "$python_bin" ]; then
    brew_bin="$(find_brew || true)"
    if [ -z "$brew_bin" ]; then
      install_homebrew
      brew_bin="$(find_brew || true)"
    fi
    [ -n "$brew_bin" ] || fail 'Homebrew is still unavailable. Install Python 3.11 from https://www.python.org/downloads/macos/'
    echo 'Installing Python 3.11 with Homebrew...'
    "$brew_bin" install python@3.11
    python_bin="$("$brew_bin" --prefix python@3.11)/bin/python3.11"
    valid_python "$python_bin" || fail 'Python 3.11 installation did not produce a usable interpreter.'
  fi
fi

echo '[2/5] Checking the project virtual environment...'
if ! valid_python "$venv_python"; then
  echo 'Creating or repairing .venv...'
  "$python_bin" -m venv --clear .venv
fi
valid_python "$venv_python" || fail 'The virtual environment Python is not usable after creation.'

echo '[3/5] Checking pip and installing required packages...'
if ! "$venv_python" -m pip --version >/dev/null 2>&1; then
  "$venv_python" -m ensurepip --upgrade
fi
"$venv_python" -m pip install --disable-pip-version-check --prefer-binary -r requirements.txt
if ! check_project_imports "$venv_python"; then
  echo 'A package is installed but cannot be imported. Repairing dependencies...'
  "$venv_python" -m pip install --disable-pip-version-check --prefer-binary --force-reinstall -r requirements.txt
  check_project_imports "$venv_python" || fail 'Required Python packages still cannot be imported after repair.'
fi
"$venv_python" -m pip check

echo '[4/5] Preparing the database without replacing saved data...'
"$venv_python" seed.py --if-empty

if [ "${1:-}" = '--setup-only' ]; then
  echo 'Environment is ready. Run ./start_mac.command to start the server.'
  exit 0
fi

echo '[5/5] Starting the local server...'
exec "$venv_python" run_server.py
