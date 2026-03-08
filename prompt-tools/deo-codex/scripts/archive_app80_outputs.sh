#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
archive_root="${1:-$repo_root/archived-result/$(date +%Y%m%d_%H%M%S)_before_app80_10x_rerun}"

mkdir -p "$archive_root"

declare -a rel_paths=(
  "DEO-PNG/App80 DEO"
  "DEO-MARKDOWN/App80 DEO"
  "DEO-SEGMENTS/App80 DEO"
)

moved=0
for rel in "${rel_paths[@]}"; do
  src="$repo_root/$rel"
  if [[ -e "$src" ]]; then
    dst="$archive_root/$rel"
    mkdir -p "$(dirname "$dst")"
    mv "$src" "$dst"
    echo "Archived: $rel"
    moved=$((moved + 1))
  fi
done

if [[ -d "$repo_root/DEO-DATABASE" ]]; then
  mkdir -p "$archive_root/DEO-DATABASE"
  shopt -s nullglob
  for db in "$repo_root"/DEO-DATABASE/*.csv; do
    cp "$db" "$archive_root/DEO-DATABASE/"
    echo "Snapshot DB: $(basename "$db")"
  done
  shopt -u nullglob
fi

mkdir -p "$repo_root/DEO-PNG" "$repo_root/DEO-MARKDOWN" "$repo_root/DEO-SEGMENTS"

echo "Archive root: $archive_root"
echo "Moved sets: $moved"
