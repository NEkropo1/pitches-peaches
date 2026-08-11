#!/usr/bin/env sh
# Install PitchesPeaches. Detects uv, installs it if missing, then installs the
# tool. No sudo, no system package manager, no PATH surgery beyond uv's own.
set -eu

if ! command -v uv >/dev/null 2>&1; then
    echo "uv not found — installing it from astral.sh"
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # uv's installer puts it here and appends to your shell profile for next time.
    for dir in "$HOME/.local/bin" "$HOME/.cargo/bin"; do
        [ -x "$dir/uv" ] && PATH="$dir:$PATH" && export PATH && break
    done
fi

if ! command -v uv >/dev/null 2>&1; then
    echo "uv still isn't on PATH. Open a new shell and run this again." >&2
    exit 1
fi

uv tool install pitches-peaches

echo
echo "Installed. Set your key, then run:"
echo
echo "  export ANTHROPIC_API_KEY=sk-ant-..."
echo "  peaches run https://the-job-posting --cv ~/cv.pdf"
