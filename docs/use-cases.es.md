# Casos de uso

Cada caso indica la situación, el comando y qué comprobar. La instalación y la lista completa de opciones están en el [README](../README.md), en inglés. [English version](use-cases.en.md).

## Cómo elegir

| Tienes | Quieres | Ve a |
|---|---|---|
| Un diseño sobre fondo blanco o liso | Solo el diseño, para cualquier fondo | [1](#1-quitar-el-fondo-y-conservar-todo-lo-demás) |
| Arte negro o de un color, con blanco dentro de las letras | Solo la tinta | [2](#2-hacer-transparente-también-el-blanco-interior) |
| Un logo pequeño o una captura | Una versión que escale | [3](#3-rescatar-un-logo-pequeño-o-borroso) |
| Un diseño con colores corporativos exactos | Esos valores exactos en el archivo | [4](#4-usar-colores-corporativos-exactos) |
| Un cartel o diseño a sangre | Una copia vectorial, con su fondo | [5](#5-conservar-una-imagen-completa-sin-fondo-que-quitar) |
| Un archivo para plóter de corte o serigrafía | Colores que nunca se solapen | [6](#6-preparar-un-archivo-para-plóter-de-corte-o-serigrafía) |
| Demasiados tonos parecidos | Una paleta más simple | [7](#7-reducir-el-número-de-colores) |
| Un resultado roto o dentado | Uno mejor | [8](#8-corregir-detalle-perdido-o-bordes-dentados) |
| Una foto o una pintura | | [9](#9-cuándo-flattrace-no-es-la-herramienta-adecuada) |

Antes de enviar nada a imprenta o producción, abre la vista previa, y también el informe si el diseño tiene detalles finos.

## 1. Quitar el fondo y conservar todo lo demás

**Situación.** Una invitación o un billete con una tarjeta beige y un contorno oscuro, sobre una página blanca. Quieres la tarjeta sin la página. Quitar «todos los píxeles claros» destruiría la tarjeta beige y cualquier cosa pálida que tenga dentro.

```sh
flattrace billete.png
```

Solo se quita el color conectado con el borde de la imagen, de modo que una tarjeta beige dentro de un contorno sigue opaca, aunque sea casi blanca. Los colores se detectan solos. El mapa de `examples/france-map` es este caso.

**Comprueba.** La vista previa muestra el resultado sobre un color de contraste. El exterior debe verse de ese color y la tarjeta, sólida.

## 2. Hacer transparente también el blanco interior

**Situación.** Un diseño de letras negras para una camiseta o una pegatina. El blanco de dentro de las letras también debe desaparecer; si no, se verán parches blancos sobre una camiseta de color.

```sh
flattrace letras.jpg
```

Si flattrace encuentra zonas encerradas que parecen fondo, las mantiene opacas y te dice qué hacer:

```
Warning: Interior areas colored #FBFBFB look like the background but stayed opaque.
To make them transparent too, add --also-transparent '#FBFBFB'.
```

```sh
flattrace letras.jpg --also-transparent '#FBFBFB' --force
```

**Comprueba.** Dentro de las letras, la vista previa debe mostrar el color de contraste. `examples/clapperboard/knockout.svg` es este caso.

## 3. Rescatar un logo pequeño o borroso

**Situación.** Solo tienes un PNG pequeño de una web antigua, o una captura en JPEG.

```sh
flattrace logo-antiguo.png
```

Las imágenes pequeñas se amplían antes de trazarlas y los bordes se suavizan, así que el resultado escala bien. flattrace no puede inventar lo que el archivo no contiene: el texto de menos de unos 10 píxeles se convierte en manchas. `examples/clapperboard` parte de 113 píxeles de ancho: sus formas grandes salen limpias y sus etiquetas diminutas se pierden.

**Comprueba.** Compara los detalles ampliados del informe. Plantéate volver a escribir el texto pequeño sobre el resultado en un programa de diseño.

## 4. Usar colores corporativos exactos

**Situación.** La imagen de origen es un JPEG, de modo que su azul marino mide `#03162F`, mientras que el corporativo es `#04162E`.

```sh
flattrace logo.jpg --colors '#04162E,#BB100F,#FEF3E1'
```

Cada color detectado se convierte en el más cercano de tu lista, y todas las capas usan exactamente esos valores. Aparecen avisos si un color detectado queda lejos de todos los tuyos, o si uno de los tuyos no coincide con nada, lo que suele indicar un valor mal escrito.

**Comprueba.** La lista `layers` de la salida debe mostrar solo tus colores.

## 5. Conservar una imagen completa, sin fondo que quitar

**Situación.** Un cartel que ocupa toda la imagen y se va a reimprimir en grande.

```sh
flattrace cartel.jpg --background keep
```

Sin la opción, flattrace detecta que el borde no es de un color uniforme, no quita nada y te avisa. Con `--background keep` indicas que eso es lo que quieres. `examples/poster` es este caso: una serigrafía de los años 30 reducida a ocho tonos.

**Comprueba.** Los degradados reales se convierten en bandas. En el ejemplo, la transición del cielo tiene un borde ruidoso, que de lejos no molesta pero puede necesitar un retoque.

## 6. Preparar un archivo para plóter de corte o serigrafía

**Situación.** Cada color se cortará en vinilo o se imprimirá con su propia pantalla, así que un color no debe continuar debajo de otro.

```sh
flattrace pegatina.png --layers cutout
```

Cada color aparece solo donde es visible. Cada grupo `<g id="color-N">` del SVG se puede seleccionar y enviar por separado.

**Comprueba.** En pantalla, pueden verse líneas muy finas entre colores en el modo `cutout`. Es la forma en que los visores dibujan los bordes que se tocan, no un hueco del archivo. Para imprimir o para pantalla, usa mejor el modo por defecto, `stacked`. Añade el reventado que pida tu imprenta.

## 7. Reducir el número de colores

**Situación.** Se han detectado siete tonos y pagas por tres tintas.

```sh
flattrace dibujo.png --colors 3
```

Los colores más cercanos se fusionan hasta que quedan tres, y el fondo no cuenta.

**Comprueba.** Al fusionar, dos zonas vecinas pueden quedar del mismo color y perderse el límite entre ellas. Si ocurre, elige tú los colores como en el caso 4.

## 8. Corregir detalle perdido o bordes dentados

**Situación.** Las líneas finas salen rotas o el detalle fino empastado, o bien los contornos se ven ondulados.

```sh
flattrace dibujo.png --detail high --force   # conserva más detalle pequeño
flattrace dibujo.png --detail low --force    # da contornos más suaves
```

**Comprueba.** Compara los detalles ampliados del informe en las dos versiones. Las métricas por sí solas pueden pasar por alto líneas rotas, así que míralo.

## 9. Cuándo flattrace no es la herramienta adecuada

**Situación.** Una foto, una pintura con sombreado, una ilustración suave con aerógrafo.

```sh
flattrace pintura.png
# flattrace: error: image not suitable for flat-color tracing: 20 colors found; ...
# código de salida 3
```

`examples/shaded-painting` se rechaza de esta forma. Aplanarla produciría miles de manchas sin sentido, así que flattrace se detiene en lugar de escribir un archivo malo. Para conseguir a propósito un efecto de cartel, puedes forzarlo con `--colors 6`, sabiendo que obtendrás eso. Si no, conserva esas imágenes en formato de mapa de bits.

## Para scripts y asistentes de IA

Añade `--json` a cualquier comando y lee el código de salida. El README incluye el [procedimiento a seguir](../README.md#using-flattrace-from-an-ai-assistant).

```sh
for archivo in logos/*.png; do
  flattrace "$archivo" --json > "${archivo%.png}.result.json" || echo "falló: $archivo"
done
```

Revisa cada vista previa. Que un lote termine sin errores no significa que el resultado sea bueno.
