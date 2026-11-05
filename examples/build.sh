#!/usr/bin/env sh
# Regenerates every example output. Run from the repository root with flattrace installed.
set -u
cd "$(dirname "$0")"

flattrace france-map/input.png -o france-map/result.svg --force
flattrace poster/input.jpg --background keep -o poster/result.svg --force
flattrace clapperboard/input.png -o clapperboard/result.svg --force
flattrace clapperboard/input.png --also-transparent '#FDFDFD' -o clapperboard/knockout.svg --force

# This one is refused on purpose, with exit code 3.
flattrace shaded-painting/input.png -o shaded-painting/result.svg --force
echo "shaded-painting exit code: $? (3 expected)"
