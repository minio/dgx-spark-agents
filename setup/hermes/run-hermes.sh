#!/bin/bash
# Ask Hermes Agent one question about a read-only source tree, inside bubblewrap.
# The whole filesystem is mounted read-only except Hermes's own state and an
# empty temp directory, and Hermes gets only its file tools (no terminal).
#
#   run-hermes.sh <source-dir> "<question>" [session-id]
set -euo pipefail
src=$1 question=$2 session=${3:-}
tmp=${HERMES_TMP:-/tmp/hermes-tmp}
mkdir -p "$tmp"
exec bwrap --ro-bind / / --dev /dev --proc /proc \
  --bind "$HOME/.hermes" "$HOME/.hermes" \
  --bind "$tmp" "$tmp" --setenv TMPDIR "$tmp" \
  --die-with-parent -- \
  hermes -z "$question" -t file --in "$src" ${session:+--resume "$session"}
