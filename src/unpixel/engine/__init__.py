"""The color and contour engine.

Stages: `classify` (pixel art, hard geometry or soft art), `labels` (denoise, antialiasing, background,
palette, assignment), `planar` (shared walls between regions), `curves` (corners, smoothing, Bezier fit),
`svgout` (paths). `pipeline` ties them together and records the time of each stage.
"""
