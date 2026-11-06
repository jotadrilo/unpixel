# Ejemplos y casos de uso

Cada ejemplo muestra la entrada real, la salida real y el comando exacto. La instalación y la lista completa de opciones están en el [README principal](../README.md), en inglés. [English version](README.md).

Las salidas se muestran sobre un color de prueba, que no forma parte del SVG. Los comandos se ejecutan desde esta carpeta, y [`build.sh`](build.sh) los regenera todos. Los créditos de las imágenes están en [`CREDITS.md`](CREDITS.md).

## Por defecto: sin ninguna opción

Casi todo el arte de colores planos solo necesita el nombre del archivo. Estos cuatro usan `unpixel input.png`, con colores y fondo detectados automáticamente.

| Entrada | Salida | Detectado |
|---|---|---|
| <img src="coffee/input.png" width="300" alt="Letras negras: Coffee is like a hug in a mug"> | <img src="coffee/result.preview.png" width="300" alt="Las mismas letras sin fondo"> | Negro y blanco, en 682 × 1024 px. El blanco de «HUG» y de la taza se queda. Para quitarlo, mira el [caso 2](#2-hacer-transparente-también-el-blanco-interior). |
| <img src="car/input.png" width="300" alt="Coche rosa con un árbol de Navidad"> | <img src="car/result.preview.png" width="300" alt="El mismo coche sin fondo, con sus adornos intactos"> | Diez colores, hasta los pequeños adornos del árbol. |
| <img src="award/input.png" width="300" alt="Escarapela roja y azul"> | <img src="award/result.preview.png" width="300" alt="La misma escarapela sin fondo, con sus finas costuras"> | Tres colores, con el aro fino, las estrellas y las costuras. |
| <img src="snow-globe/input.png" width="300" alt="Muñeco de nieve en una bola de nieve"> | <img src="snow-globe/result.preview.png" width="300" alt="La misma bola de nieve sin fondo"> | Doce colores, incluidos los dos azules parecidos del cristal y su aro. |

## Cómo elegir

| Tienes | Quieres | Ve a |
|---|---|---|
| Un diseño sobre fondo blanco o liso | Solo el diseño, para cualquier fondo | [1](#1-quitar-el-fondo-y-conservar-todo-lo-demás) |
| Letras negras o de un color, con blanco dentro | Solo la tinta | [2](#2-hacer-transparente-también-el-blanco-interior) |
| Un logo pequeño o una captura | Una versión que escale | [3](#3-rescatar-un-logo-pequeño-o-borroso) |
| Un diseño con colores corporativos exactos | Esos valores exactos en el archivo | [4](#4-usar-colores-corporativos-exactos) |
| Un cartel o diseño a sangre | Una copia vectorial, con su fondo | [5](#5-conservar-una-imagen-completa-sin-fondo-que-quitar) |
| Un archivo para plóter de corte o serigrafía | Colores que nunca se solapen | [6](#6-preparar-un-archivo-para-plóter-de-corte-o-serigrafía) |
| Demasiados tonos parecidos | Una paleta más simple | [7](#7-reducir-el-número-de-colores) |
| Un resultado roto o dentado | Uno mejor | [8](#8-corregir-detalle-perdido-o-bordes-dentados) |
| Una foto o una pintura | Saber qué esperar | [9](#9-cuándo-unpixel-no-es-la-herramienta-adecuada) |
| Un diseño para una superficie oscura o de color | Verlo ahí y recolorearlo | [10](#10-comprobar-y-recolorear-para-la-superficie-de-destino) |
| Tu propio diseño con una marca de agua de borrador | Saber qué le ocurrirá | [11](#11-diseños-con-marca-de-agua) |
| Cualquier diseño | Solo sus líneas, para colorear o cortar | [12](#12-quedarte-solo-con-las-líneas) |

Antes de enviar nada a imprenta o producción, abre la vista previa, y también el informe si el diseño tiene detalles finos.

## 1. Quitar el fondo y conservar todo lo demás

**Situación.** Un sello, billete o invitación con zonas pálidas, sobre una página blanca. Quieres el diseño sin la página. Quitar «todos los píxeles claros» destruiría el marco pálido y cualquier cosa clara que tenga dentro.

```sh
unpixel stamp/input.jpg -o stamp/result.svg
unpixel badge/input.png -o badge/result.svg
```

| Entrada | Salida |
|---|---|
| <img src="stamp/input.jpg" width="340" alt="Sello postal sobre una página blanca"> | <img src="stamp/result.preview.png" width="340" alt="El sello solo. El marco pálido sigue sólido"> |
| <img src="badge/input.png" width="340" alt="Insignia negra con el centro blanco"> | <img src="badge/result.preview.png" width="340" alt="La insignia sola. El exterior y los huecos entre los rayos quedan libres, y el centro encerrado sigue sólido"> |

Solo se quita el color conectado con el borde de la imagen. El sello conserva su marco pálido y los seis colores detectados. En la insignia, el centro casi blanco sigue opaco porque lo encierra el contorno, aunque sea del mismo color que la página, mientras que los huecos entre los rayos llegan al exterior y desaparecen.

**Comprueba.** El exterior debe mostrar el color de prueba, y las zonas pálidas encerradas deben verse sólidas.

**El límite de esta regla.** Para unpixel, una zona pálida sin contorno que toca el exterior parece fondo:

```sh
unpixel sleigh/input.png -o sleigh/result.svg
```

| Entrada | Salida: la barba y la piel han desaparecido |
|---|---|
| <img src="sleigh/input.png" width="340" alt="Papá Noel en un trineo, con barba blanca y piel pálida sin contorno"> | <img src="sleigh/result.preview.png" width="340" alt="El mismo trineo, con la barba y la piel transparentes"> |

Ninguna opción las separa, porque en la imagen se conectan de verdad. Usa `--background keep` para una copia opaca, o parte de una versión con contorno o con un fondo de color más marcado.

## 2. Hacer transparente también el blanco interior

**Situación.** Letras negras para una camiseta o una pegatina. El blanco de dentro de las letras también debe desaparecer; si no, se verán parches blancos sobre una camiseta de color.

```sh
unpixel family/input.png -o family/result.svg
```

unpixel mantiene opacas las zonas encerradas que parecen fondo y te dice qué hacer:

```
Warning: Interior areas colored #F8F6F5 look like the background but stayed opaque.
To make them transparent too, add --also-transparent '#F8F6F5'.
  Run: unpixel family/input.png -o family/result.svg --also-transparent '#F8F6F5' --force
```

```sh
unpixel family/input.png --also-transparent '#F8F6F5' -o family/knockout.svg
```

| Entrada | Por defecto: el blanco encerrado se queda | Con `--also-transparent` |
|---|---|---|
| <img src="family/input.png" width="260" alt="Family is everything, letras negras"> | <img src="family/result.preview.png" width="260" alt="Letras que aún tienen blanco dentro"> | <img src="family/knockout.preview.png" width="260" alt="Letras solo con tinta negra"> |

Fíjate en «is» y «EVERYTHING»: en la última imagen, las letras son huecos.

**Comprueba.** Dentro de las letras, la vista previa debe mostrar el color de prueba. Las marcas finas que se confunden con el blanco desaparecen con él.

## 3. Rescatar un logo pequeño o borroso

**Situación.** Solo tienes un PNG pequeño de una web antigua, o una captura en JPEG.

```sh
unpixel clapperboard/input.png -o clapperboard/result.svg
```

| Entrada, 113 px de ancho, aquí ampliada | Salida |
|---|---|
| <img src="clapperboard/input.png" width="340" alt="Icono diminuto y borroso de una claqueta"> | <img src="clapperboard/result.preview.png" width="340" alt="Claqueta limpia con bordes suaves"> |

Las imágenes pequeñas se amplían antes de trazarlas y los bordes se suavizan, así que el resultado escala bien. unpixel no puede inventar lo que el archivo no contiene: las formas grandes salen limpias y el sombreado suave pasa a dos tonos planos, pero las etiquetas de pocos píxeles se convierten en manchas, y las franjas blancas de arriba llegan al exterior, así que quedan transparentes.

**Comprueba.** Compara los detalles ampliados del informe. Plantéate volver a escribir el texto pequeño sobre el resultado en un programa de diseño.

## 4. Usar colores corporativos exactos

**Situación.** Necesitas valores exactos en el archivo, como los de tu marca, en lugar de los medidos en la imagen.

```sh
unpixel france-map/input.png -o france-map/result.svg
unpixel france-map/input.png --colors '#F26A21,#0B7A3B,#7A0019,#7F77E8,#101010,#1747D1' -o france-map/brand.svg
```

| Entrada | Colores detectados | Tus colores |
|---|---|---|
| <img src="france-map/input.png" width="260" alt="Mapa de Francia con regiones de colores"> | <img src="france-map/result.preview.png" width="260" alt="El mismo mapa con sus colores originales"> | <img src="france-map/brand.preview.png" width="260" alt="El mismo mapa con los colores de marca"> |

| Detectado | `#FF7D41` | `#007D00` | `#790000` | `#867DFF` | `#000000` | `#0000FF` |
|---|---|---|---|---|---|---|
| **Salida** | `#F26A21` | `#0B7A3B` | `#7A0019` | `#7F77E8` | `#101010` | `#1747D1` |

Cada color detectado se convierte en el más cercano de tu lista, y todas las capas usan exactamente esos valores. Aparecen avisos si un color detectado queda lejos de todos los tuyos, como aquí el azul, o si uno de los tuyos no coincide con nada, lo que suele indicar un valor mal escrito.

**Comprueba.** La lista `layers` de la salida debe mostrar solo tus colores.

## 5. Conservar una imagen completa, sin fondo que quitar

**Situación.** Un cartel que ocupa toda la imagen y se va a reimprimir en grande.

```sh
unpixel poster/input.jpg --background keep -o poster/result.svg
```

| Entrada | Salida: ocho tonos planos |
|---|---|
| <img src="poster/input.jpg" width="340" alt="Cartel See America de los años 30"> | <img src="poster/result.preview.png" width="340" alt="El mismo cartel en ocho tonos planos"> |

Sin la opción, unpixel detecta que el borde no es de un color uniforme, no quita nada y te avisa. Con `--background keep` indicas que eso es lo que quieres.

**Comprueba.** Los degradados reales se convierten en bandas. A la izquierda del cielo, la transición tiene un borde ruidoso, que de lejos no molesta pero puede necesitar un retoque.

## 6. Preparar un archivo para plóter de corte o serigrafía

**Situación.** Cada color se cortará en vinilo o se imprimirá con su propia pantalla, así que un color no debe continuar debajo de otro.

```sh
unpixel airmail/input.jpg --background keep --colors '#0C1331,#CC3407,#F59562,#FDEDAA' --layers cutout -o airmail/cutout.svg
python plates.py airmail/cutout.svg airmail/plates.png
```

| Entrada | Los cuatro colores, cada uno por separado |
|---|---|
| <img src="airmail/input.jpg" width="240" alt="Cartel Air Mail de los años 20"> | <img src="airmail/plates.png" width="620" alt="Cuatro planchas: fondo azul marino con las formas recortadas, flechas rojas, letras naranjas y letras crema"> |

Cada color aparece solo donde es visible: en la plancha azul, todas las demás formas son huecos. Cada grupo `<g id="color-N">` del SVG se puede seleccionar y enviar por separado, y [`plates.py`](plates.py) los dibuja así.

**Comprueba.** Las capas recortadas dejan huecos diminutos donde se tocan los colores, porque cada forma se curva por separado. Aquí suman el 0,08 % de la imagen, y unpixel avisa de ello. Los impresos envejecidos también dejan marcas: la sombra de la izquierda vuelve roja parte de la «O», y se ven halos tenues de un color en los demás. Límpialas a mano antes de producir, y añade el reventado que pida tu imprenta. Para imprimir o para pantalla, usa mejor el modo por defecto, `stacked`.

## 7. Reducir el número de colores

**Situación.** Un impreso envejecido tiene decenas de tonos casi idénticos, y pagas por cuatro tintas.

```sh
unpixel airmail/input.jpg --background keep -o airmail/result.svg
# unpixel: error: image not suitable for flat-color tracing: 17 colors found; ...
# código de salida 3
unpixel airmail/input.jpg --background keep --colors 6 -o airmail/six-colors.svg
unpixel airmail/input.jpg --background keep --colors '#0C1331,#CC3407,#F59562,#FDEDAA' -o airmail/four-colors.svg
unpixel airmail/input.jpg --background keep --colors '#0C1331,#CC3407,#F59562,#FDEDAA,#D9562B' -o airmail/shaded-orange.svg
```

| Entrada | `--colors 6` | Cuatro colores indicados | Cinco, con el naranja en sombra |
|---|---|---|---|
| <img src="airmail/input.jpg" width="200" alt="Cartel Air Mail envejecido, con una sombra a la izquierda"> | <img src="airmail/six-colors.preview.png" width="200" alt="Seis colores, con el fondo manchado y la sombra aún presentes"> | <img src="airmail/four-colors.preview.png" width="200" alt="Cuatro colores, con el fondo plano. La O tiene un trozo rojo"> | <img src="airmail/shaded-orange.preview.png" width="200" alt="Cinco colores. Overnight es de un naranja uniforme"> |

El envejecimiento del papel hace que unpixel vea 17 colores, así que por defecto se detiene. Hay dos formas de reducirlos:

- **Un número** fusiona los colores más cercanos hasta que quedan esos. Es rápido, pero sigue la distancia entre colores, no su significado: aquí conserva dos azules y la sombra.
- **Colores indicados** te dan el control, y cada color detectado pasa al más cercano de tu lista. Es la mejor opción para impresos envejecidos.

La sombra de la izquierda de este cartel oscurece el naranja hasta acercarlo al rojo: de ahí el trozo rojo de la «O». Añadir ese naranja oscuro como quinto color lo arregla. Para terminar con un solo naranja, edita el `fill` de ese grupo en el SVG. Un escaneado plano con luz uniforme evita el problema desde el principio.

**Comprueba.** Al fusionar, dos zonas vecinas pueden quedar del mismo color y perderse el límite entre ellas.

### Una ilustración con sombreado suave

**Situación.** Una ilustración parece plana, pero sus brillos y bordes suaves suman más tonos de los que unpixel acepta por defecto. Es habitual en imágenes generadas. Aquí es la mascota de unpixel, con brillos en el casco, el planeta y la cara.

```sh
unpixel axolotl/input.png -o axolotl/result.svg
# unpixel: error: image not suitable for flat-color tracing: 20 colors found; ...
# código de salida 3
unpixel axolotl/input.png --colors 8 --preview-background '#C9D2FF' -o axolotl/result.svg
```

| Entrada | `--colors 8`, sobre un color de comprobación |
|---|---|
| <img src="axolotl/input.png" width="400" alt="Ajolote astronauta surfeando una tostada voladora, con un ovni y un planeta, sobre blanco"> | <img src="axolotl/result.preview.png" width="400" alt="La misma ilustración en ocho colores planos, sin fondo y con sus bigotes, estrellas y migas intactos"> |

Aquí un número funciona bien, porque los tonos están claramente agrupados. Los bigotes finos, las estrellas y las migas se conservan, mientras que el sombreado de la tostada y de la llama se funde en color plano. El resultado avisa de que las zonas blancas dentro de la ilustración se han quedado opacas, que es lo correcto para los ojos y los brillos, así que aquí se mantienen.

El logo del [README principal](../README.md) es este mismo `result.svg`, con solo su `viewBox` recortado a la ilustración.

## 8. Corregir detalle perdido o bordes dentados

**Situación.** Las líneas finas salen rotas o el detalle fino empastado, o bien los contornos se ven ondulados.

```sh
unpixel ornament/input.png --detail low -o ornament/low.svg
unpixel ornament/input.png -o ornament/medium.svg
unpixel ornament/input.png --detail high -o ornament/high.svg
```

De izquierda a derecha: entrada, `low`, `medium` y `high`, ampliados ×3.

<img src="ornament/comparison.png" alt="El mismo ornamento en cuatro niveles. Low da formas más gruesas y simples. High conserva más detalle pequeño">

`low` da formas más tranquilas y gruesas y elimina marcas pequeñas: mira el ala y la cinta. `high` conserva más del rayado fino y de la cara, y también más ondulación. Aquí, la capa negra del ornamento completo pasa de 155 formas en `low` a 293 en `medium` y 332 en `high`.

**Comprueba.** Compara recortes ampliados, como este. Las métricas pueden pasar por alto líneas rotas, así que míralo.

## 9. Cuándo unpixel no es la herramienta adecuada

**Situación.** Una foto, una pintura con sombreado, una ilustración suave con aerógrafo.

```sh
unpixel shaded-painting/input.png -o shaded-painting/result.svg
# unpixel: error: image not suitable for flat-color tracing: 20 colors found; ...
# código de salida 3
unpixel shaded-painting/input.png --colors 6 -o shaded-painting/forced.svg
```

| Entrada: rechazada por defecto | Forzada con `--colors 6` |
|---|---|
| <img src="shaded-painting/input.png" width="340" alt="Dinosaurio pintado con sombreado suave"> | <img src="shaded-painting/forced.preview.png" width="340" alt="El mismo dinosaurio en seis colores planos, como una serigrafía"> |

unpixel se detiene en lugar de aplanar el sombreado sin avisar. Forzar una paleta reducida funciona y puede quedar bien, pero es una versión estilizada de cartel, no una copia fiel: el sombreado suave de la piel desaparece. Si necesitas una copia fiel, conserva la imagen en formato de mapa de bits.

**Comprueba.** Decide si ese aspecto de cartel es lo que quieres.

## 10. Comprobar y recolorear para la superficie de destino

**Situación.** Un logo oscuro para una pegatina en un portátil oscuro. La vista previa por defecto usa un color elegido para mostrar defectos, así que puede verse bien aunque el logo apenas se note en la superficie real.

```sh
unpixel family/input.png --also-transparent '#F8F6F5' --preview-background '#1C1C1E' -o family/on-dark.svg
unpixel family/input.png --also-transparent '#F8F6F5' --colors '#F2F2F2' --preview-background '#1C1C1E' -o family/light-on-dark.svg
```

| Entrada | Sobre la superficie real: apenas se ve | Recoloreado |
|---|---|---|
| <img src="family/input.png" width="260" alt="Family is everything, letras negras"> | <img src="family/on-dark.preview.png" width="260" alt="Letras negras casi invisibles sobre gris oscuro"> | <img src="family/light-on-dark.preview.png" width="260" alt="Letras claras bien legibles sobre gris oscuro"> |

El primer comando muestra el diseño sobre esa superficie. El segundo lo aclara: con un solo valor en `--colors`, todos los colores pasan a ser ese valor. Con varios colores, indica un sustituto por color o edita el `fill` de cada grupo en el SVG. `--preview-background` nunca cambia el SVG.

**Comprueba.** La vista previa debe leerse con claridad sobre el color real de la superficie. unpixel no mide el contraste.

## 11. Diseños con marca de agua

**Situación.** Tu propio diseño, o uno sobre el que tienes derechos, aún lleva una marca «SAMPLE» de borrador, y quieres saber qué le ocurrirá.

unpixel no tiene ninguna función para marcas de agua. La marca son simplemente más píxeles, así que el resultado depende de su intensidad. Estas entradas llevan una marca añadida para este proyecto, en tres intensidades:

```sh
unpixel watermark/faint.png -o watermark/faint.svg
unpixel watermark/medium.png -o watermark/medium.svg
unpixel watermark/strong.png -o watermark/strong.svg
```

| Marca | Entrada | Salida | Qué ocurrió |
|---|---|---|---|
| Suave | <img src="watermark/faint.png" width="280" alt="Mapa con una marca SAMPLE suave"> | <img src="watermark/faint.preview.png" width="280" alt="Mapa sin marca visible"> | Queda dentro de los colores existentes, así que desaparece. |
| Media | <img src="watermark/medium.png" width="280" alt="Mapa con una marca SAMPLE visible"> | <img src="watermark/medium.preview.png" width="280" alt="Mapa con fragmentos de la marca en las zonas naranjas"> | Se queda a trozos y añade un séptimo color falso. |
| Fuerte | <img src="watermark/strong.png" width="280" alt="Mapa con una marca SAMPLE oscura"> | <img src="watermark/strong.preview.png" width="280" alt="Mapa con toda la marca trazada como formas"> | Se queda entera, trazada como formas, con doce colores en total. |

Indicar la paleta real elimina los colores falsos, aunque no la forma de la marca allí donde es tan fuerte que pasa a otro color:

```sh
unpixel watermark/medium.png --colors '#FF7D41,#007D00,#790000,#867DFF,#000000,#0000FF' -o watermark/medium-palette.svg
```

<img src="watermark/medium-palette.preview.png" width="340" alt="Mapa con los seis colores originales">

unpixel no avisa de nada de esto, porque no puede distinguir una marca de agua del dibujo.

**Comprueba.** Mira la vista previa. Si tienes el original sin la marca, úsalo: siempre es mejor punto de partida.

**Derechos.** Úsalo solo con imágenes propias o que tengas permiso para usar. Una marca de agua suele indicar que la imagen necesita licencia, y perder la marca al trazarla no te la concede. Quitarla de una obra ajena puede ser ilegal por sí mismo.

## 12. Quedarte solo con las líneas

**Situación.** Quieres una página para colorear, una plantilla o un trazado para un plóter, sin rellenos.

```sh
unpixel axolotl/input.png --colors 8 --outline lines --preview-background '#C9D2FF' -o axolotl/lines.svg
unpixel axolotl/input.png --colors 8 --outline edges --preview-background '#C9D2FF' -o axolotl/edges.svg
```

| Entrada | `--outline lines` | `--outline edges` |
|---|---|---|
| <img src="axolotl/input.png" width="260" alt="Ajolote astronauta a todo color"> | <img src="axolotl/lines.preview.png" width="260" alt="El mismo ajolote en contornos negros limpios, sin rellenos"> | <img src="axolotl/edges.preview.png" width="260" alt="El mismo ajolote con una línea fina en cada frontera entre colores"> |

- **`lines`** conserva solo las formas del color más oscuro. Va bien con ilustraciones que ya tienen contorno, como esta. Si no lo tienen, el color más oscuro es un relleno, y unpixel te avisa.
- **`edges`** dibuja una línea donde se tocan dos colores, así que funciona con ilustraciones planas sin contorno. Un contorno existente tiene dos lados, así que sale como línea doble, como aquí. El grosor se ajusta con `--outline-width`, en píxeles de la imagen original.

Ambos escriben una sola capa, en el color más oscuro. Para cambiarlo, edita el `fill` de ese grupo en el SVG.

**Comprueba.** En una vista previa pequeña, las líneas finas pueden ocultar cortes. Abre el informe si las líneas deben ser continuas, por ejemplo para un plóter.

## Para scripts y asistentes de IA

Añade `--json` a cualquier comando y lee el código de salida. El README incluye el [procedimiento a seguir](../README.md#using-unpixel-from-an-ai-assistant).

```sh
for archivo in logos/*.png; do
  unpixel "$archivo" --json > "${archivo%.png}.result.json" || echo "falló: $archivo"
done
```

Revisa cada vista previa. Que un lote termine sin errores no significa que el resultado sea bueno.
