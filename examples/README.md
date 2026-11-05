# Examples and use cases

Every example here shows the real input, the real output and the exact command. Installation and the full list of options are in the [main README](../README.md). [Versión en español](README.es.md).

Outputs are shown on a check color, which is not part of the SVG. Commands run from this folder, and [`build.sh`](build.sh) regenerates all of them. Image credits are in [`CREDITS.md`](CREDITS.md).

## The default: no options at all

Most flat-color artwork needs nothing but the file name. These four use `unpixel input.png`, with colors and background detected automatically.

| Input | Output | Detected |
|---|---|---|
| <img src="coffee/input.png" width="300" alt="Black lettering: Coffee is like a hug in a mug"> | <img src="coffee/result.preview.png" width="300" alt="The same lettering with no background"> | Black and white, on 682 × 1024 px. The white inside "HUG" and the cup stays. To remove it, see [case 2](#2-make-enclosed-white-see-through-too). |
| <img src="car/input.png" width="300" alt="Pink car carrying a Christmas tree"> | <img src="car/result.preview.png" width="300" alt="The same car with no background, with its ornaments intact"> | Ten colors, down to the small tree ornaments. |
| <img src="award/input.png" width="300" alt="Red and blue award rosette"> | <img src="award/result.preview.png" width="300" alt="The same rosette with no background, with its thin stitching"> | Three colors, keeping the thin ring, stars and stitching. |
| <img src="snow-globe/input.png" width="300" alt="Snowman in a snow globe"> | <img src="snow-globe/result.preview.png" width="300" alt="The same snow globe with no background"> | Twelve colors, including the two similar blues of the glass and its rim. |

## Choosing a case

| You have | You want | Go to |
|---|---|---|
| A design on a white or plain background | The design alone, for any background | [1](#1-remove-the-background-and-keep-everything-else) |
| Black or one-color lettering, with white inside it | Nothing but the ink | [2](#2-make-enclosed-white-see-through-too) |
| A small logo or a screenshot of one | A version that scales | [3](#3-rescue-a-small-or-blurry-logo) |
| A design with exact brand colors | Those exact values in the file | [4](#4-use-exact-brand-colors) |
| A poster or full-bleed design | A vector copy, background included | [5](#5-keep-a-full-image-with-no-background-to-remove) |
| A file for a cutter, plotter or screen printer | Colors that never overlap | [6](#6-prepare-a-file-for-a-cutter-plotter-or-screen-printing) |
| Too many similar tones | A simpler palette | [7](#7-reduce-the-number-of-colors) |
| A broken or jagged result | A better one | [8](#8-fix-lost-detail-or-jagged-edges) |
| A photo or painting | To know what to expect | [9](#9-when-unpixel-is-the-wrong-tool) |
| A design for a dark or colored surface | To see it there, and recolor it | [10](#10-check-and-recolor-for-the-surface-it-goes-on) |
| Your own artwork with a draft watermark | To know what will happen to it | [11](#11-artwork-with-a-watermark) |

Before sending anything to print or production, open the preview, and the report if the design has fine detail.

## 1. Remove the background and keep everything else

**Situation.** A stamp, ticket or invitation with pale areas, on a white page. You want the design without the page. Removing "all light pixels" would destroy the pale frame and anything light inside it.

```sh
unpixel stamp/input.jpg -o stamp/result.svg
unpixel badge/input.png -o badge/result.svg
```

| Input | Output |
|---|---|
| <img src="stamp/input.jpg" width="340" alt="Postage stamp on a white page"> | <img src="stamp/result.preview.png" width="340" alt="Stamp alone. The pale frame stays solid"> |
| <img src="badge/input.png" width="340" alt="Black badge with a white center"> | <img src="badge/result.preview.png" width="340" alt="Badge alone. The outside and the gaps between its rays are clear, the enclosed center stays solid"> |

Only the color connected to the image border is removed. The stamp keeps its pale frame and six detected colors. On the badge, the near-white center stays opaque because the outline encloses it, even though it is the same color as the page, while the gaps between the rays reach the outside and disappear.

**Check.** The outside should show the check color, and enclosed pale areas should be solid.

**The limit of this rule.** A pale area with no outline, touching the outside, looks like background to unpixel:

```sh
unpixel sleigh/input.png -o sleigh/result.svg
```

| Input | Output: the beard and the skin are gone |
|---|---|
| <img src="sleigh/input.png" width="340" alt="Santa on a sleigh, with a white beard and pale skin with no outline"> | <img src="sleigh/result.preview.png" width="340" alt="The same sleigh, with the beard and the skin see-through"> |

No option separates them, because in the image they really do connect. Use `--background keep` for an opaque copy, or start from a version with an outline or a stronger background color.

## 2. Make enclosed white see-through too

**Situation.** Black lettering for a T-shirt or a sticker. White inside the letters must disappear too, or the design shows white patches on a colored shirt.

```sh
unpixel family/input.png -o family/result.svg
```

unpixel keeps enclosed areas that look like the background opaque, and tells you what to do:

```
Warning: Interior areas colored #F8F6F5 look like the background but stayed opaque.
To make them transparent too, add --also-transparent '#F8F6F5'.
  Run: unpixel family/input.png -o family/result.svg --also-transparent '#F8F6F5' --force
```

```sh
unpixel family/input.png --also-transparent '#F8F6F5' -o family/knockout.svg
```

| Input | Default: enclosed white stays | With `--also-transparent` |
|---|---|---|
| <img src="family/input.png" width="260" alt="Family is everything, black lettering"> | <img src="family/result.preview.png" width="260" alt="Lettering with white still inside the letters"> | <img src="family/knockout.preview.png" width="260" alt="Lettering with nothing but black ink"> |

Look at "is" and "EVERYTHING": in the last image, the letters are holes.

**Check.** Inside the letters, the preview should show the check color. Thin marks that blend into the white go with it.

## 3. Rescue a small or blurry logo

**Situation.** All you have is a small PNG from an old website, or a JPEG screenshot.

```sh
unpixel clapperboard/input.png -o clapperboard/result.svg
```

| Input, 113 px wide, enlarged here | Output |
|---|---|
| <img src="clapperboard/input.png" width="340" alt="Tiny blurred clapperboard icon"> | <img src="clapperboard/result.preview.png" width="340" alt="Clean clapperboard with smooth edges"> |

Small images are enlarged before tracing and edges are smoothed, so the result scales cleanly. unpixel cannot invent what the file does not contain: the large shapes are clean, and the soft shading becomes two flat tones, but labels of a few pixels become blobs, and the white stripes at the top reach the outside, so they become transparent.

**Check.** Compare the close-ups in the report. Consider retyping small text over the result in a design program.

## 4. Use exact brand colors

**Situation.** You need exact values in the file, such as your brand's, instead of what was measured in the image.

```sh
unpixel france-map/input.png -o france-map/result.svg
unpixel france-map/input.png --colors '#F26A21,#0B7A3B,#7A0019,#7F77E8,#101010,#1747D1' -o france-map/brand.svg
```

| Input | Colors detected | Your colors |
|---|---|---|
| <img src="france-map/input.png" width="260" alt="Map of France with colored regions"> | <img src="france-map/result.preview.png" width="260" alt="Same map with its original colors"> | <img src="france-map/brand.preview.png" width="260" alt="Same map with the brand colors"> |

| Detected | `#FF7D41` | `#007D00` | `#790000` | `#867DFF` | `#000000` | `#0000FF` |
|---|---|---|---|---|---|---|
| **Output** | `#F26A21` | `#0B7A3B` | `#7A0019` | `#7F77E8` | `#101010` | `#1747D1` |

Each detected color becomes the closest in your list, and every layer uses exactly those values. Warnings appear if a detected color is far from all of yours, as blue was here, or if one of yours matched nothing, which usually means a mistyped value.

**Check.** The `layers` list in the output should show only your colors.

## 5. Keep a full image with no background to remove

**Situation.** A poster that fills the whole image, to be reprinted large.

```sh
unpixel poster/input.jpg --background keep -o poster/result.svg
```

| Input | Output: eight flat tones |
|---|---|
| <img src="poster/input.jpg" width="340" alt="See America poster from the 1930s"> | <img src="poster/result.preview.png" width="340" alt="Same poster in eight flat tones"> |

Without the flag, unpixel notices that the border is not one uniform color, removes nothing and warns you. Use `--background keep` to say that this is what you want.

**Check.** Real gradients become bands. On the left of the sky, the transition has a noisy edge, which is fine at a distance but may need retouching.

## 6. Prepare a file for a cutter, plotter or screen printing

**Situation.** Each color will be cut from vinyl or printed as its own screen, so a color must not continue underneath another.

```sh
unpixel airmail/input.jpg --background keep --colors '#0C1331,#CC3407,#F59562,#FDEDAA' --layers cutout -o airmail/cutout.svg
python plates.py airmail/cutout.svg airmail/plates.png
```

| Input | The four colors, each one alone |
|---|---|
| <img src="airmail/input.jpg" width="240" alt="Air Mail poster from the 1920s"> | <img src="airmail/plates.png" width="620" alt="Four plates: navy background with the shapes cut out, red arrows, orange lettering, cream lettering"> |

Each color appears only where it is visible: on the navy plate, every other shape is a hole. Each `<g id="color-N">` group in the SVG can be selected and sent separately, and [`plates.py`](plates.py) draws them like this.

**Check.** Cutout layers leave tiny gaps where colors meet, because each shape is curved separately. Here they add up to 0.08% of the image, and unpixel warns about them. Aged print also leaves marks: the shadow on the left turns part of the "O" red, and faint halos of one color show on the others. Clean those up by hand before production, and add the trapping your print shop requires. For print or screen use, prefer the default, `stacked`.

## 7. Reduce the number of colors

**Situation.** An aged print has dozens of near-identical tones, and you are paying for four inks.

```sh
unpixel airmail/input.jpg --background keep -o airmail/result.svg
# unpixel: error: image not suitable for flat-color tracing: 17 colors found; ...
# exit code 3
unpixel airmail/input.jpg --background keep --colors 6 -o airmail/six-colors.svg
unpixel airmail/input.jpg --background keep --colors '#0C1331,#CC3407,#F59562,#FDEDAA' -o airmail/four-colors.svg
unpixel airmail/input.jpg --background keep --colors '#0C1331,#CC3407,#F59562,#FDEDAA,#D9562B' -o airmail/shaded-orange.svg
```

| Input | `--colors 6` | Four named colors | Five, adding the shaded orange |
|---|---|---|---|
| <img src="airmail/input.jpg" width="200" alt="Aged Air Mail poster with a shadow on the left"> | <img src="airmail/six-colors.preview.png" width="200" alt="Six colors, with the blotchy background and the shadow still present"> | <img src="airmail/four-colors.preview.png" width="200" alt="Four colors, with a flat background. The O has a red patch"> | <img src="airmail/shaded-orange.preview.png" width="200" alt="Five colors. Overnight is one even orange"> |

Paper aging makes unpixel see 17 colors, so it stops by default. There are two ways to reduce them:

- **A number** merges the closest colors until that many remain. It is quick, but it follows color distance and not meaning: here it keeps two blues and the shadow.
- **Named colors** give you control, and each detected color becomes the closest one you list. This is the better choice for aged prints.

The shadow on the left of this poster darkens the orange until it is closer to red, which is the red patch in the "O". Adding that darker orange as a fifth color fixes it. To end with one orange, edit that group's `fill` in the SVG. A flat scan with even lighting avoids the problem altogether.

**Check.** Merging can make two neighboring areas the same color, losing the boundary between them.

### An illustration with soft shading

**Situation.** An illustration looks flat, but its highlights and soft edges add up to more tones than unpixel accepts by default. This is common in generated artwork. Here it is unpixel's mascot, with shine on the helmet, the planet and the face.

```sh
unpixel axolotl/input.png -o axolotl/result.svg
# unpixel: error: image not suitable for flat-color tracing: 20 colors found; ...
# exit code 3
unpixel axolotl/input.png --colors 8 --preview-background '#C9D2FF' -o axolotl/result.svg
```

| Input | `--colors 8`, on a check color |
|---|---|
| <img src="axolotl/input.png" width="400" alt="Axolotl astronaut surfing a flying slice of toast, with a UFO and a planet, on white"> | <img src="axolotl/result.preview.png" width="400" alt="The same illustration in eight flat colors, with no background and its whiskers, stars and crumbs intact"> |

A number works well here, since the tones are clearly grouped. Thin whiskers, stars and crumbs stay, while the shading on the toast and the flame merges into flat color. The result warns that white areas inside the artwork stayed opaque, which is right for the eyes and the highlights, so this one keeps them.

The logo in the [main README](../README.md) is this same `result.svg`, with only its `viewBox` cropped to the artwork.

## 8. Fix lost detail or jagged edges

**Situation.** Thin lines are broken or fine detail is clogged, or else outlines are visibly wavy.

```sh
unpixel ornament/input.png --detail low -o ornament/low.svg
unpixel ornament/input.png -o ornament/medium.svg
unpixel ornament/input.png --detail high -o ornament/high.svg
```

From left to right: input, `low`, `medium` and `high`, enlarged 3×.

<img src="ornament/comparison.png" alt="The same ornament at four levels. Low gives bolder, simpler shapes. High keeps the most small detail">

`low` gives calmer, bolder shapes and drops small marks: see the wing and the ribbon. `high` keeps more of the fine hatching and the face, and it also keeps more wobble. Here, the black layer of the whole ornament goes from 155 shapes in `low` to 293 in `medium` and 332 in `high`.

**Check.** Compare enlarged crops, as above. Metrics can miss broken lines, so look.

## 9. When unpixel is the wrong tool

**Situation.** A photo, a shaded painting, a soft airbrushed illustration.

```sh
unpixel shaded-painting/input.png -o shaded-painting/result.svg
# unpixel: error: image not suitable for flat-color tracing: 20 colors found; ...
# exit code 3
unpixel shaded-painting/input.png --colors 6 -o shaded-painting/forced.svg
```

| Input: refused by default | Forced with `--colors 6` |
|---|---|
| <img src="shaded-painting/input.png" width="340" alt="Painted dinosaur with soft shading"> | <img src="shaded-painting/forced.preview.png" width="340" alt="Same dinosaur in six flat colors, like a screen print"> |

unpixel stops instead of silently flattening the shading. Forcing a reduced palette works, and it can look good, but it is a stylized poster version and not a faithful copy: the soft skin shading is gone. If you need a faithful copy, keep the image as raster.

**Check.** Decide whether the poster look is what you want.

## 10. Check and recolor for the surface it goes on

**Situation.** A dark logo for a sticker on a dark laptop. The default preview uses a color chosen to show defects, so it can look fine even though the logo will barely show on the real surface.

```sh
unpixel family/input.png --also-transparent '#F8F6F5' --preview-background '#1C1C1E' -o family/on-dark.svg
unpixel family/input.png --also-transparent '#F8F6F5' --colors '#F2F2F2' --preview-background '#1C1C1E' -o family/light-on-dark.svg
```

| Input | On the real surface: barely visible | Recolored |
|---|---|---|
| <img src="family/input.png" width="260" alt="Family is everything, black lettering"> | <img src="family/on-dark.preview.png" width="260" alt="Black lettering nearly invisible on dark grey"> | <img src="family/light-on-dark.preview.png" width="260" alt="Light lettering clearly readable on dark grey"> |

The first command shows the design on that surface. The second turns it light: with one value in `--colors`, every color becomes that value. With several colors, list one replacement per color, or edit each group's `fill` in the SVG. `--preview-background` never changes the SVG.

**Check.** The preview should read clearly on the real surface color. unpixel does not measure contrast.

## 11. Artwork with a watermark

**Situation.** Your own design, or one you have the rights to, still has a draft "SAMPLE" overlay, and you want to know what will happen to it.

unpixel has no watermark feature. The overlay is just more pixels, so the result depends on its strength. These inputs have an overlay added for this project, at three strengths:

```sh
unpixel watermark/faint.png -o watermark/faint.svg
unpixel watermark/medium.png -o watermark/medium.svg
unpixel watermark/strong.png -o watermark/strong.svg
```

| Overlay | Input | Output | What happened |
|---|---|---|---|
| Faint | <img src="watermark/faint.png" width="280" alt="Map with a faint SAMPLE overlay"> | <img src="watermark/faint.preview.png" width="280" alt="Map with no visible overlay"> | Falls within the existing colors, so it vanishes. |
| Medium | <img src="watermark/medium.png" width="280" alt="Map with a visible SAMPLE overlay"> | <img src="watermark/medium.preview.png" width="280" alt="Map with fragments of the overlay left in the orange areas"> | Stays in fragments, and adds a false seventh color. |
| Strong | <img src="watermark/strong.png" width="280" alt="Map with a dark SAMPLE overlay"> | <img src="watermark/strong.preview.png" width="280" alt="Map with the whole overlay traced as shapes"> | Stays whole, traced as shapes, with twelve colors in total. |

Naming the real palette removes the false colors, though not the shape of the overlay where it is strong enough to cross into another color:

```sh
unpixel watermark/medium.png --colors '#FF7D41,#007D00,#790000,#867DFF,#000000,#0000FF' -o watermark/medium-palette.svg
```

<img src="watermark/medium-palette.preview.png" width="340" alt="Map with the original six colors">

unpixel gives no warning about any of this, because it cannot tell a watermark from artwork.

**Check.** Look at the preview. If you have the original without the overlay, use it, as that is always the better source.

**Rights.** Use this only on images you own or have permission to use. A watermark usually means the image needs a license, and losing the mark during tracing does not grant one. Removing one from someone else's work can be illegal in itself.

## For scripts and AI assistants

Add `--json` to any command, and read the exit code. The README has the [workflow to follow](../README.md#using-unpixel-from-an-ai-assistant).

```sh
for file in logos/*.png; do
  unpixel "$file" --json > "${file%.png}.result.json" || echo "failed: $file"
done
```

Review each preview. A batch that finishes cleanly is not the same as a batch that looks right.
