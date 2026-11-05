#!/usr/bin/env sh
# Regenerates every example output. Run with unpixel installed, for example:
#   PATH="$PWD/.venv/bin:$PATH" examples/build.sh
set -u
cd "$(dirname "$0")"
u="unpixel --force"

# 1. Remove the background and keep everything else
$u stamp/input.jpg -o stamp/result.svg
$u badge/input.png -o badge/result.svg

# 2. Make enclosed white see-through too
$u family/input.png -o family/result.svg
$u family/input.png --also-transparent '#F8F6F5' -o family/knockout.svg

# 3. Rescue a small or blurry logo
$u clapperboard/input.png -o clapperboard/result.svg

# 4. Use exact brand colors
$u france-map/input.png -o france-map/result.svg
$u france-map/input.png --colors '#F26A21,#0B7A3B,#7A0019,#7F77E8,#101010,#1747D1' -o france-map/brand.svg

# 5. Keep a full image with no background to remove
$u poster/input.jpg --background keep -o poster/result.svg

# 6. Prepare a file for a cutter, plotter or screen printing
$u airmail/input.jpg --background keep --colors 4 --layers cutout -o airmail/cutout.svg
python plates.py airmail/cutout.svg airmail/plates.png

# 7. Reduce the number of colors. Aged paper gives too many tones, so the first run is refused with exit code 3.
$u airmail/input.jpg --background keep -o airmail/result.svg
echo "airmail exit code: $? (3 expected)"
$u airmail/input.jpg --background keep --colors 4 -o airmail/four-colors.svg

# 8. Fix lost detail or jagged edges
$u ornament/input.png --detail low -o ornament/low.svg
$u ornament/input.png -o ornament/medium.svg
$u ornament/input.png --detail high -o ornament/high.svg
python compare.py ornament/comparison.png 90,190,330,450 ornament/input.png ornament/low.svg ornament/medium.svg ornament/high.svg

# 9. When unpixel is the wrong tool. Refused on purpose, with exit code 3.
$u shaded-painting/input.png -o shaded-painting/result.svg
echo "shaded-painting exit code: $? (3 expected)"
$u shaded-painting/input.png --colors 6 -o shaded-painting/forced.svg

# 10. Check and recolor for the surface it goes on
$u family/input.png --also-transparent '#F8F6F5' --preview-background '#1C1C1E' -o family/on-dark.svg
$u family/input.png --also-transparent '#F8F6F5' --colors '#F2F2F2' --preview-background '#1C1C1E' -o family/light-on-dark.svg

# 11. Artwork with a watermark
$u watermark/faint.png -o watermark/faint.svg
$u watermark/medium.png -o watermark/medium.svg
$u watermark/medium.png --colors '#FF7D41,#007D00,#790000,#867DFF,#000000,#0000FF' -o watermark/medium-palette.svg
$u watermark/strong.png -o watermark/strong.svg
