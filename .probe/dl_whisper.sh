#!/usr/bin/env bash
set -euo pipefail
REPO="$1"; DEST="$2"
BASE="https://hf-mirror.com/$REPO/resolve/main"
mkdir -p "$DEST"
for f in config.json model.bin tokenizer.json vocabulary.txt preprocessor_config.json; do
  if [ -f "$DEST/$f" ]; then echo "skip $f"; continue; fi
  echo "get $f"
  curl -sL --fail --retry 3 -o "$DEST/$f" "$BASE/$f" || rm -f "$DEST/$f"
done
ls -la "$DEST"
