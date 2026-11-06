"""Prototype color and contour engine. Local only until the owner validates it on the battery.

Stages: `classify` (pixel art, hard geometry or soft art), `labels` (denoise, antialiasing, background,
palette, assignment), `planar` (shared walls between regions), `curves` (corners, smoothing, Bezier fit),
`svgout` (paths). `pipeline` ties them together and records the time of each stage.
"""
