"""Hand-drawn diagrams, and the page parts both languages share. Text goes through `tr`, so one drawing serves both."""

from __future__ import annotations

from draw import tr

# The one place that mentions the CLI's flag and default. Delete it, and {{usage_note}} in the templates, when the
# default changes.
USAGE_NOTE = tr(
    "<b>Using it today.</b> Everything here describes unpixel's engine in <code>src/unpixel/engine/</code>. On the command line that behavior needs <code>--engine new</code>, because <code>classic</code> is still the CLI's default.",
    "<b>Para usarlo hoy.</b> Todo lo que sigue describe el motor de unpixel en <code>src/unpixel/engine/</code>. En la línea de órdenes ese comportamiento requiere <code>--engine new</code>, porque <code>classic</code> sigue siendo la opción predeterminada.",
)


def raster_vector():
    return f"""<svg class="dg" viewBox="0 0 600 200" role="img" aria-label="{tr('The same shape as a pixel grid and as a curve with nodes', 'La misma forma como rejilla de píxeles y como curva con nodos')}">
<g fill="var(--s1)" stroke="var(--paper)" stroke-width="1">
<rect x="60" y="30" width="20" height="20"/><rect x="80" y="30" width="20" height="20"/><rect x="100" y="30" width="20" height="20"/>
<rect x="40" y="50" width="20" height="20"/><rect x="60" y="50" width="20" height="20"/><rect x="80" y="50" width="20" height="20"/><rect x="100" y="50" width="20" height="20"/><rect x="120" y="50" width="20" height="20"/>
<rect x="40" y="70" width="20" height="20"/><rect x="60" y="70" width="20" height="20"/><rect x="80" y="70" width="20" height="20"/><rect x="100" y="70" width="20" height="20"/><rect x="120" y="70" width="20" height="20"/><rect x="140" y="70" width="20" height="20"/>
<rect x="60" y="90" width="20" height="20"/><rect x="80" y="90" width="20" height="20"/><rect x="100" y="90" width="20" height="20"/><rect x="120" y="90" width="20" height="20"/><rect x="140" y="90" width="20" height="20"/>
<rect x="80" y="110" width="20" height="20"/><rect x="100" y="110" width="20" height="20"/><rect x="120" y="110" width="20" height="20"/>
</g>
<text x="100" y="165" text-anchor="middle" class="dt">{tr('Raster: 22 colored squares', 'Ráster: 22 cuadrados de color')}</text>
<path d="M360 40C400 25 440 45 470 85C490 112 450 140 410 128C370 116 335 75 360 40Z" fill="var(--s1)"/>
<g stroke="var(--s2)" fill="none"><path d="M360 40L400 25M470 85L440 45M470 85L490 112M410 128L450 140M410 128L370 116M360 40L335 75"/></g>
<g fill="var(--paper)" stroke="var(--ink)" stroke-width="1.5"><circle cx="360" cy="40" r="4"/><circle cx="470" cy="85" r="4"/><circle cx="410" cy="128" r="4"/></g>
<g fill="var(--s2)"><circle cx="400" cy="25" r="2.5"/><circle cx="440" cy="45" r="2.5"/><circle cx="490" cy="112" r="2.5"/><circle cx="450" cy="140" r="2.5"/><circle cx="370" cy="116" r="2.5"/><circle cx="335" cy="75" r="2.5"/></g>
<text x="410" y="165" text-anchor="middle" class="dt">{tr('Vector: 3 nodes, 3 curves, 1 color', 'Vector: 3 nodos, 3 curvas, 1 color')}</text>
</svg>"""


def pipeline():
    steps = [
        ("<code>classify</code>", tr("<code>pixel</code> takes an exact shortcut", "<code>pixel</code> toma un atajo exacto")),
        ("<code>perceptual</code>", tr("compressed Lab", "Lab comprimido")),
        ("<code>bilateral</code>, <code>flatten_gradients</code>", tr("not on <code>hard</code>", "no en <code>hard</code>")),
        ("<code>transition_mask</code>", tr("who is a mix", "quién es mezcla")),
        ("<code>find_background</code>", tr("flood from the border", "inundación desde el borde")),
        ("<code>build_palette</code>", tr("two passes; uses <code>highlight_mask</code>", "dos pasadas; usa <code>highlight_mask</code>")),
        ("<code>assign</code>", tr("reach 9; background, 3", "alcance 9; fondo, 3")),
        ("<code>dissolve_fringes</code>", ""),
        ("<code>settle_colors</code>", tr("each color, the median of what it got", "cada color, la mediana de lo suyo")),
        ("<code>refine_double</code>", tr("map at 2×", "mapa a ×2")),
        ("<code>absorb_specks</code>, <code>dissolve_speckle</code>, <code>drop_floating_pale</code>", ""),
        ("<code>planar.build</code>", tr("walls and junctions", "paredes y cruces")),
        ("<code>_subpixel</code>, <code>find_corners</code>", ""),
        ("<code>smooth_chains</code>, <code>fit_chains</code>", ""),
        ("<code>write_svg</code>", tr("fills and trap strokes", "rellenos y trazos trampa")),
    ]
    items = "".join(f"<li>{a}{f' <small>{b}</small>' if b else ''}</li>" for a, b in steps)
    return f'<div class="pipes"><ol class="pipe n">{items}</ol></div>'


def farthest():
    points = '<circle cx="60" cy="70" r="3"/><circle cx="72" cy="85" r="3"/><circle cx="50" cy="90" r="3"/><circle cx="85" cy="65" r="3"/><circle cx="95" cy="88" r="3"/><circle cx="62" cy="105" r="3"/><circle cx="110" cy="75" r="3"/><circle cx="80" cy="110" r="3"/><circle cx="120" cy="100" r="3"/><circle cx="100" cy="115" r="3"/><circle cx="240" cy="40" r="3"/><circle cx="360" cy="70" r="3"/><circle cx="375" cy="70" r="3"/><circle cx="360" cy="85" r="3"/><circle cx="375" cy="85" r="3"/><circle cx="405" cy="75" r="3"/><circle cx="420" cy="90" r="3"/><circle cx="395" cy="95" r="3"/><circle cx="430" cy="68" r="3"/><circle cx="440" cy="92" r="3"/><circle cx="410" cy="110" r="3"/><circle cx="455" cy="78" r="3"/><circle cx="425" cy="115" r="3"/><circle cx="465" cy="102" r="3"/><circle cx="445" cy="118" r="3"/><circle cx="585" cy="40" r="3"/>'
    return f"""<svg class="dg" viewBox="0 0 600 180" role="img" aria-label="{tr('K-means spreads centers by area; farthest point picks what is different', 'K-means reparte centros por área; punto más lejano elige lo distinto')}">
<g fill="var(--muted)">{points}</g>
<g fill="none" stroke="var(--s2)" stroke-width="2"><path d="M70 80l10 10m0 -10l-10 10"/><path d="M100 90l10 10m0 -10l-10 10"/></g>
<g fill="none" stroke="var(--s1)" stroke-width="2"><path d="M415 85l10 10m0 -10l-10 10"/><circle cx="585" cy="40" r="9"/></g>
<text x="150" y="150" text-anchor="middle" class="dt">{tr('K-means: two centers in the cloud,', 'K-means: dos centros en la nube,')}</text><text x="150" y="168" text-anchor="middle" class="dt">{tr('and none for the lone point', 'y ninguno para el punto solitario')}</text>
<text x="470" y="150" text-anchor="middle" class="dt">{tr('Farthest point:', 'Punto más lejano:')}</text><text x="470" y="168" text-anchor="middle" class="dt">{tr('the lone point gets its color', 'el solitario tiene su color')}</text>
</svg>"""


def mix():
    return f"""<svg class="dg" viewBox="0 0 600 170" role="img" aria-label="{tr('A pixel p projected onto the segment between a and b', 'Un píxel p se proyecta sobre el segmento entre a y b')}">
<line x1="70" y1="110" x2="530" y2="110" stroke="var(--ink)" stroke-width="2"/>
<circle cx="70" cy="110" r="9" fill="#1c152b" stroke="var(--ink)"/><circle cx="530" cy="110" r="9" fill="#fbbbce" stroke="var(--ink)"/>
<text x="70" y="140" text-anchor="middle" class="dt">a</text><text x="530" y="140" text-anchor="middle" class="dt">b</text>
<circle cx="260" cy="72" r="8" fill="#a4768a" stroke="var(--ink)"/><text x="260" y="55" text-anchor="middle" class="dt">p</text>
<line x1="260" y1="80" x2="260" y2="110" stroke="var(--s2)" stroke-width="2" stroke-dasharray="4 3"/>
<text x="268" y="98" class="dts">{tr('residual: distance from p to the line', 'residuo: distancia de p a la recta')}</text>
<path d="M70 124H260" stroke="var(--s1)" stroke-width="3"/><text x="165" y="139" text-anchor="middle" class="dts">{tr('u: position between a and b', 'u: posición entre a y b')}</text>
<text x="300" y="24" text-anchor="middle" class="dt">{tr('p is a mix if 0.12 &lt; u &lt; 0.88 and the residual is small', 'p es mezcla si 0,12 &lt; u &lt; 0,88 y el residuo es pequeño')}</text>
</svg>"""


def walls():
    return f"""<svg class="dg" viewBox="0 0 620 180" role="img" aria-label="{tr('Two separate outlines against one shared wall', 'Dos trazados separados frente a una pared compartida')}">
<g transform="translate(20 10)"><path d="M0 0H130C150 40 120 90 145 140H0Z" fill="var(--s1)" fill-opacity=".55"/><path d="M270 0H134C158 42 112 88 150 140H270Z" fill="var(--s2)" fill-opacity=".55"/><text x="135" y="160" text-anchor="middle" class="dt">{tr('Two curves: they cross, with gaps and overlaps', 'Dos curvas: se cruzan, con huecos y solapes')}</text></g>
<g transform="translate(330 10)"><path d="M0 0H130C150 40 120 90 145 140H0Z" fill="var(--s1)" fill-opacity=".55"/><path d="M270 0H130C150 40 120 90 145 140H270Z" fill="var(--s2)" fill-opacity=".55"/><path d="M130 0C150 40 120 90 145 140" fill="none" stroke="var(--ink)" stroke-width="2.5"/><text x="135" y="160" text-anchor="middle" class="dt">{tr('One curve: they fit by definition', 'Una curva: por definición, encajan')}</text></g>
</svg>"""


def trap():
    return f"""<svg class="dg" viewBox="0 0 620 170" role="img" aria-label="{tr('Cross section: lower fill, stroke along the wall, upper fill', 'Corte por capas: relleno inferior, trazo sobre la pared, relleno superior')}">
<rect x="310" y="20" width="270" height="26" fill="var(--s2)"/><text x="330" y="38" class="dts" style="fill:#fff">{tr('3. upper fill (on top)', '3. relleno superior (encima)')}</text>
<rect x="270" y="58" width="80" height="26" fill="var(--s1)" opacity=".7"/><text x="262" y="76" text-anchor="end" class="dts">{tr('2. trap stroke, centered on the wall', '2. trazo trampa, centrado en la pared')}</text>
<rect x="40" y="96" width="270" height="26" fill="var(--s1)"/><text x="50" y="114" class="dts" style="fill:#fff">{tr('1. lower fill (below)', '1. relleno inferior (debajo)')}</text>
<line x1="310" y1="8" x2="310" y2="138" stroke="var(--ink)" stroke-dasharray="4 3"/><text x="310" y="156" text-anchor="middle" class="dt">{tr('the wall', 'la pared')}</text>
</svg>"""


def viewer(image_names, first):
    buttons = "".join(f'<button type="button" data-image="{n}">{n}</button>' for n in image_names)
    return f"""<div class="vw" id="viewer">
<div class="bar" aria-label="{tr('Image', 'Imagen')}">{buttons}</div>
<div class="row"><span>{tr('Zoom:', 'Zoom:')}</span> <button type="button" data-zoom="1">1×</button><button type="button" data-zoom="2">2×</button><button type="button" data-zoom="4">4×</button></div>
<input type="range" min="0" max="100" value="50" aria-label="{tr('Position of the split', 'Posición de la división')}">
<div class="stage"><div class="inner"><img class="base" src="{first}" alt=""><div class="over"><img src="{first}" alt=""></div><div class="rule"></div><span class="lab l" style="left:6px">{tr('Original', 'Original')}</span><span class="lab r" style="right:6px">unpixel</span></div></div>
<p class="row links"></p>
</div>"""


def all_values(image_names, first):
    return {
        "usage_note": USAGE_NOTE,
        "d_raster": raster_vector(),
        "d_pipeline": pipeline(),
        "d_farthest": farthest(),
        "d_mix": mix(),
        "d_walls": walls(),
        "d_trap": trap(),
        "d_viewer": viewer(image_names, first),
    }
