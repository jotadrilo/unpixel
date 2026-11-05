# Use cases

Each case gives the situation, the command, and what to check. Installation and the full list of options are in the [README](../README.md). [Versión en español](use-cases.es.md).

## Choosing a case

| You have | You want | Go to |
|---|---|---|
| A design on a white or plain background | The design alone, for any background | [1](#1-remove-the-background-and-keep-everything-else) |
| Black or one-color art, with white inside letters | Nothing but the ink | [2](#2-make-enclosed-white-see-through-too) |
| A small logo or a screenshot of one | A version that scales | [3](#3-rescue-a-small-or-blurry-logo) |
| A design with exact brand colors | Those exact values in the file | [4](#4-use-exact-brand-colors) |
| A poster or full-bleed design | A vector copy, background included | [5](#5-keep-a-full-image-with-no-background-to-remove) |
| A file for a cutter, plotter or screen printer | Colors that never overlap | [6](#6-prepare-a-file-for-a-cutter-plotter-or-screen-printing) |
| Too many similar tones | A simpler palette | [7](#7-reduce-the-number-of-colors) |
| A broken or jagged result | A better one | [8](#8-fix-lost-detail-or-jagged-edges) |
| A photo or painting | | [9](#9-when-flattrace-is-the-wrong-tool) |

Before sending anything to print or production, open the preview, and the report if the design has fine detail.

## 1. Remove the background and keep everything else

**Situation.** An invitation or a ticket with a cream card and a dark outline, on a white page. You want the card without the page. Removing "all light pixels" would destroy the cream card and anything pale inside it.

```sh
flattrace ticket.png
```

Only the color connected to the image border is removed, so a cream card inside an outline stays opaque, even when it is nearly white. Colors are detected for you. The map in `examples/france-map` is this case.

**Check.** The preview shows the result on a contrasting color. The outside should be that color and the card should be solid.

## 2. Make enclosed white see-through too

**Situation.** A black lettering design for a T-shirt or a sticker. White inside the letters must disappear too, or the design shows white patches on a colored shirt.

```sh
flattrace lettering.jpg
```

If flattrace finds enclosed areas that look like the background, it keeps them opaque and tells you what to do:

```
Warning: Interior areas colored #FBFBFB look like the background but stayed opaque.
To make them transparent too, add --also-transparent '#FBFBFB'.
```

```sh
flattrace lettering.jpg --also-transparent '#FBFBFB' --force
```

**Check.** Inside the letters, the preview should show the check color. `examples/clapperboard/knockout.svg` is this case.

## 3. Rescue a small or blurry logo

**Situation.** All you have is a small PNG from an old website, or a JPEG screenshot.

```sh
flattrace old-logo.png
```

Small images are enlarged before tracing and edges are smoothed, so the result scales cleanly. flattrace cannot invent what the file does not contain: text smaller than about 10 pixels turns into blobs. `examples/clapperboard` starts from 113 pixels wide, and its large shapes are clean while its tiny labels are lost.

**Check.** Compare the close-ups in the report. Consider retyping small text over the result in a design program.

## 4. Use exact brand colors

**Situation.** The source is a JPEG, so its navy measures `#03162F` while the brand navy is `#04162E`.

```sh
flattrace logo.jpg --colors '#04162E,#BB100F,#FEF3E1'
```

Each detected color becomes the closest color in your list, and every layer uses exactly those values. Warnings appear if a detected color is far from all of yours, or if one of yours matched nothing, which usually means a mistyped value.

**Check.** The `layers` list in the output should show only your colors.

## 5. Keep a full image with no background to remove

**Situation.** A poster that fills the whole image, to be reprinted large.

```sh
flattrace poster.jpg --background keep
```

Without the flag, flattrace notices that the border is not one uniform color, removes nothing and warns you. Use `--background keep` to say that this is what you want. `examples/poster` is this case: a 1930s screen print reduced to eight tones.

**Check.** Real gradients become bands. In the example, the transition in the sky has a noisy edge, which is fine at a distance but may need retouching.

## 6. Prepare a file for a cutter, plotter or screen printing

**Situation.** Each color will be cut from vinyl or printed as its own screen, so a color must not continue underneath another.

```sh
flattrace sticker.png --layers cutout
```

Each color appears only where it is visible. Each `<g id="color-N">` group in the SVG can be selected and sent separately.

**Check.** On screen, hairlines may appear between colors in `cutout` mode. That is how viewers draw touching edges, and it is not a gap in the file. For print or screen use, prefer the default, `stacked`. Add trapping as your print shop requires.

## 7. Reduce the number of colors

**Situation.** Detection found seven tones and you are paying for three inks.

```sh
flattrace artwork.png --colors 3
```

The closest colors merge until three remain, and the background does not count.

**Check.** Merging can make two neighboring areas the same color, losing the boundary between them. If that happens, pick the colors yourself as in case 4.

## 8. Fix lost detail or jagged edges

**Situation.** Thin lines are broken or fine detail is clogged, or else outlines are visibly wavy.

```sh
flattrace artwork.png --detail high --force   # keeps more small detail
flattrace artwork.png --detail low --force    # gives smoother outlines
```

**Check.** Compare the close-ups in the report for the two versions. Metrics alone can miss broken lines, so look.

## 9. When flattrace is the wrong tool

**Situation.** A photo, a shaded painting, a soft airbrushed illustration.

```sh
flattrace painting.png
# flattrace: error: image not suitable for flat-color tracing: 20 colors found; ...
# exit code 3
```

`examples/shaded-painting` is refused this way. Flattening it would produce thousands of meaningless blobs, so flattrace stops instead of writing a bad file. For a deliberate poster effect, you can force it with `--colors 6`, knowing that this is what you get. Otherwise, keep such images as raster.

## For scripts and AI assistants

Add `--json` to any command, and read the exit code. The README has the [workflow to follow](../README.md#using-flattrace-from-an-ai-assistant).

```sh
for file in logos/*.png; do
  flattrace "$file" --json > "${file%.png}.result.json" || echo "failed: $file"
done
```

Review each preview. A batch that finishes cleanly is not the same as a batch that looks right.
