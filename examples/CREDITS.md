# Example image credits

No third-party example images remain. The inputs are the following.

## Made for this project

`axolotl/input.png`, the project's mascot, and the axolotl images in [`../battery/`](../battery/README.md) (`chef`, `diver`, `float`, `ghost`, `leaves`, `sunset` and `watchmaker`) were generated with Google Gemini for this project. `sunset.png`, and faintly `leaves.png`, carry Gemini's sparkle in a corner.

These were made from those images by [`derive.py`](derive.py), which `build.sh` runs:

| Files | Source | Changes |
|---|---|---|
| `small/chef-480.jpg`, `small/chef-220.jpg` | `chef.png` | Reduced, and saved as low-quality JPEG |
| `grain/input.png` | `chef.png` | Reduced to 700 px wide, with strong noise added |
| `pixel-art/input.png` | `axolotl/input.png` | Cropped, reduced to a grid of 176 blocks across, and limited to ten of its colors |
| `watermark/*.png` | `chef.png` | Reduced to 1000 px wide, with a "SAMPLE" overlay added at three strengths. The watermark is not anyone else's. |

## Supplied by the project owner

`../battery/principito.jpeg`, used in case 5, is an image from the battery. Its source and license are not recorded here yet.
