#!/usr/bin/env sh
# Regenerates every example, inputs made for the examples included. Run with unpixel installed, for example:
#   PATH="$PWD/.venv/bin:$PATH" examples/build.sh
set -eu
cd "$(dirname "$0")"

# The check color only changes the previews, never the SVGs. Cases about a surface set their own after it.
u="unpixel --force --preview-background #C9D2FF"
battery=../battery

python derive.py

# The default: no options at all
$u $battery/leaves.png -o leaves/result.svg
$u $battery/watchmaker.png -o watchmaker/result.svg
$u $battery/float.png -o float/result.svg

# 1. Remove the background and keep everything else
$u $battery/chef.png -o chef/result.svg
$u $battery/diver.png -o diver/result.svg

# 2. Make enclosed white see-through too
$u $battery/float.png --also-transparent '#FBFBFB' -o float/knockout.svg

# 3. Rescue a small or blurry logo
$u small/chef-480.jpg -o small/chef-480.svg
$u small/chef-220.jpg -o small/chef-220.svg

# 4. Use exact brand colors
$u axolotl/input.png --colors '#FFB800,#FFC2D6,#00B8D4,#0090A8,#FF2E7E,#6A3DF0,#14102A,#FFFFFF,#FF8A00' -o axolotl/brand.svg

# 5. Keep a full image with no background to remove
$u $battery/principito.jpeg --background keep -o principito/result.svg
$u $battery/principito.jpeg --background '#6A73BE' -o principito/no-sky.svg

# 6. Prepare a file for a cutter, plotter or screen printing
$u axolotl/input.png --colors 6 --layers cutout -o axolotl/cutout.svg
python plates.py axolotl/cutout.svg axolotl/plates.png

# 7. Reduce the number of colors
$u $battery/leaves.png --colors 10 -o leaves/ten-colors.svg
$u $battery/leaves.png --colors 6 -o leaves/six-colors.svg
$u $battery/diver.png --colors 8 -o diver/eight-colors.svg
$u axolotl/input.png --colors 8 -o axolotl/result.svg
sed 's/viewBox="0 0 1408 768" width="1408" height="768"/viewBox="359 36 697 697" width="697" height="697"/' axolotl/result.svg > axolotl/logo.svg

# 8. Fix lost detail or jagged edges
$u $battery/watchmaker.png --detail low -o watchmaker/low.svg
$u $battery/watchmaker.png --detail high -o watchmaker/high.svg
python compare.py watchmaker/comparison.png 400,540,620,660 $battery/watchmaker.png watchmaker/low.svg watchmaker/result.svg watchmaker/high.svg

# 9. Photos, paintings and noise
$u $battery/sunset.png --background keep -o sunset/result.svg
$u $battery/sunset.png --background keep --colors 6 -o sunset/six-colors.svg
$u grain/input.png -o grain/result.svg

# 10. Check and recolor for the surface it goes on
$u $battery/diver.png --preview-background '#1C1C1E' -o diver/on-dark.svg
$u $battery/diver.png --outline lines --outline-color '#F2F2F2' --preview-background '#1C1C1E' -o diver/light-lines.svg
$u $battery/ghost.png -o ghost/result.svg
$u $battery/ghost.png --preview-background '#1C1C1E' -o ghost/on-dark.svg

# 11. Artwork with a watermark
$u watermark/faint.png -o watermark/faint.svg
$u watermark/medium.png -o watermark/medium.svg
$u watermark/strong.png -o watermark/strong.svg
$u watermark/medium.png --colors '#FAD3A4,#E3A169,#FDD453,#FBBECD,#F67087,#FBB13D,#FDFDFD,#D7E4EA,#9AA7AD,#4A2636' -o watermark/medium-palette.svg

# 12. Keep only the lines
$u axolotl/input.png --colors 8 --outline lines -o axolotl/lines.svg
$u axolotl/input.png --colors 8 --outline edges -o axolotl/edges.svg
$u $battery/chef.png --colors 8 --outline edges -o chef/edges.svg
$u $battery/chef.png --colors 8 --outline edges --outline-width 4 --outline-color '#7A3CFF' -o chef/thick-edges.svg

# 13. Pixel art
$u pixel-art/input.png -o pixel-art/result.svg
