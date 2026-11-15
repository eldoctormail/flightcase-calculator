# LBD Flightcase Maker

Programa de escritorio (Python + PySide6 + OpenGL) para diseñar y fabricar flightcases a medida con las reglas de construcción del taller: placa de 10 mm, ángulo 32x32, perfil híbrido, refuerzos, tapas, bandejas, base de ruedas, herrajes del catálogo, interiores con espuma, cajones y rack 19". Lee y guarda los proyectos `.scad` del generador de OpenSCAD y arma el paquete de producción sin tener OpenSCAD instalado.

![El Taller](captura-taller.png)

---

## Funciones

- **Medidas exteriores o interiores** (primera sección del Taller): cargá el ancho, fondo y alto exterior y la app calcula las medidas interiores con las paredes, el aluminio y la espuma del armado elegido (las tapas conservan su alto), o trabajá directo con las interiores.
- **Editor del case**: todos los parámetros del generador, agrupados como en `flightcase.scad`, con su explicación al pasar el mouse. Paneles, perfiles, herrajes y avisos se recalculan al instante.
- **Estilos de case** (rack, mixer, utilitario, tapa superior, cajonera, etc.) y estilos propios guardados.
- **Interiores**: espuma en capas con calados rectangulares, redondos o con el contorno de un dibujo, huecos para los dedos, cajones, rack 19" y chequeos de choques.
- **Herrajes a mano** en cada cara, en 2D, con imán, y placas de logo desde `.svg` / `.dxf`.
- **Vista 3D** con las tapas abiertas o cerradas.
- **Paquete de producción** (`Ctrl+P`): DXF por pieza y por capa de espuma, lista de cortes y materiales en CSV, `planos.pdf`, instructivo de montaje y el case en STEP para CAD.

---

## Requisitos

- Python >= 3.14
- Sistemas operativos: Windows, macOS, Linux

### Dependencias principales

- `PySide6`: interfaz de escritorio moderna basada en Qt
- `PyOpenGL`: renderizado 3D acelerado por hardware (alambre y superficies sólidas)
- `numpy`: transformaciones geométricas 3D rápidas con vectores y matrices

Para desarrollo, `pytest` (tests automáticos) está en el grupo `dev`: `uv` lo instala solo, y con pip se instala con `pip install -e . --group dev`.

---

## Primeros pasos

### Instalar en Windows o Mac (sin Python)

Los instaladores se generan solos en GitHub (*Actions → Instaladores*). Para publicar una versión, creá una etiqueta `vX.Y.Z`: aparecen en *Releases*.

- **Windows**: `LBDFlightcaseMaker-X.Y.Z-Windows-Instalador.exe`. Si aparece «Windows protegió su PC», tocá *Más información → Ejecutar de todas formas* (el instalador todavía no está firmado).
- **Mac**: `…-macOS-AppleSilicon.dmg` (M1 o más nuevo) o `…-macOS-Intel.dmg`. Arrastrá la app a Aplicaciones. La primera vez, clic derecho sobre la app → *Abrir* (todavía no está firmada por Apple).

Los estilos de case propios se guardan en tu carpeta de usuario (`%APPDATA%\FlightcaseCalculator` en Windows, `~/Library/Application Support/FlightcaseCalculator` en Mac), así que no se pierden al actualizar.

### 1. Instalación para desarrollo

Cloná o descargá el repositorio e instalá las dependencias:

```bash
# Con uv (recomendado)
uv sync

# O con pip
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux / macOS:
source .venv/bin/activate

pip install -e .
```

### 2. Ejecutar la aplicación

- **Acceso directo en Windows**: hacé doble clic en `run.cmd` o ejecutá:
  ```cmd
  run.cmd
  ```
- **Desde la terminal**:
  ```bash
  python main.py
  # o con uv
  uv run python main.py
  ```

### 3. Ejecutar los tests

Para correr todos los tests:

```bash
uv run pytest
# o con el entorno virtual activado (después de pip install -e . --group dev):
pytest
```

En GitHub corren solos en cada PR y en cada cambio a main (`.github/workflows/tests.yml`).

---

## Reglas del taller (proyectos OpenSCAD)

`flightcase/taller/` tiene en Python las reglas de construcción del generador de OpenSCAD del taller (placa de 10 mm, ángulo 32x32, perfil híbrido, refuerzos, tapas, cubiertas, bandejas, base de ruedas, catálogo FR Sistemas / Adam Hall), más los interiores (espuma, cajones, rack 19"). En la ventana del Taller se editan todos los parámetros del generador (agrupados como en `flightcase.scad`, con su explicación al pasar el mouse) y se ven al instante los paneles, perfiles, herrajes y avisos; desde ahí se abre y se guarda el `.scad` y se exporta el paquete. También, con **Archivo → Paquete del taller desde un .scad sin abrirlo** (`Ctrl+T`) se toma un proyecto `.scad` (por ejemplo `mi_case.scad`) y se genera, sin tener OpenSCAD instalado:

- `dxf/*.dxf`: un DXF por pieza distinta, con calados (capa 0) y rebajes (capa `REBAJE`)
- `lista_cortes.csv` y `materiales.csv` (separador `;`, se abren directo en Excel)
- `planos.pdf`: piezas acotadas, aprovechamiento de placas, cortes de perfiles y materiales
- `instructivo_montaje.pdf`: perspectiva explotada y pasos de armado con sus láminas 3D (`montaje/*.png`, dibujadas por la app; el aluminio y los herrajes van simplificados)
- `case_3d.step`: el case armado en 3D para abrir en Fusion, SolidWorks o FreeCAD (ver abajo)

### Atajos del Taller

- `Ctrl+N` nuevo case, `Ctrl+O` abrir `.scad`, `Ctrl+S` guardar (sin preguntar si ya tiene archivo), `Ctrl+Shift+S` guardar como
- `Ctrl+P` exportar el paquete del taller (planos, DXF, instructivo)
- Al abrir la app se vuelve a cargar el último `.scad` que usaste, y la barra de estado muestra medidas, paneles, material y avisos del case

### Vista 3D

La barra de arriba de la vista tiene: acercar y alejar, qué hace el botón izquierdo del mouse (girar, **mano** para mover la imagen o zoom), girar 90°, vistas (isométrica, frente, atrás, lados, arriba, abajo), encuadrar, perspectiva, cotas y ejes. Además:

- Rueda del mouse: zoom hacia donde está el puntero. Botón derecho o rueda apretada: mover. Doble clic: encuadrar.
- Teclado (con la vista seleccionada): flechas giran de a 5°, Mayús + flechas mueven, `+` y `-` hacen zoom, `Inicio` o `F` encuadran.

### Ícono de la app

Sale de `packaging/icono/icono.svg`. Si lo cambiás, regenerá el `.ico` (Windows), el `.icns` (Mac) y el `.png` de la ventana con `python tools/generar_icono.py`.

### Estilos de case y herrajes del catálogo

Arriba de la pestaña Taller, **Estilo de case** aplica una forma de armado sobre las medidas que ya cargaste, sin tocar el interior ni los herrajes puestos a mano: baúl con tapa suelta, con tapa abisagrada o con base de ruedas, case de mano con pies, clamshell de dos mitades, bisagra de piano, tapa arriba y abajo, racks 19" (tapa adelante, adelante y atrás, con tapas de acceso o con cubierta que sale entera), case acostado con tapas a los costados y case liviano con perfil híbrido. Los estilos con base de ruedas la calculan solos (10 mm más chica que la planta del cuerpo, fenólico de 18 mm). Con **Guardar como estilo…** guardás cómo está armado tu case (todo menos medidas e interior) para usarlo en otros proyectos; los estilos propios van a tu carpeta de datos y aparecen con ★.

En **Herrajes del catálogo FR Sistemas** cada herraje (placa, ángulo, perfiles de cierre, esquineros, cierres, manijas, ruedas, bisagras, topes, pies, espuma, remaches…) se elige de una lista con número y nombre, filtrada por tipo; se puede escribir parte del nombre para buscar. Los artículos con * tienen medidas estimadas. En **Otros accesorios → extras** se agregan, en una tabla, artículos del catálogo para la lista de compras (asas telescópicas, argollas, tornillería, carátulas de rack…) con su cantidad.

### Exportar a STEP

Con el botón **Exportar STEP…** del Taller (o **Archivo → Exportar a STEP**, `Ctrl+Alt+S`) se guarda el case armado, con las tapas cerradas, como un ensamble STEP (AP214, en milímetros). Cada pieza es un sólido de caras planas con su nombre y su color: los paneles con sus calados pasantes, los aros y ángulos de aluminio, los esquineros, cierres, manijas y ruedas (simplificados, igual que en la vista 3D) y el interior (equipos, espuma con sus bolsillos, cajones y rack). El archivo lo escribe la app directamente, sin librerías de CAD; los tests lo validan con OpenCASCADE (el motor de FreeCAD) cuando está instalado.

### Interiores

En las secciones **Interior** de la pestaña Taller se carga lo que va adentro, en tablas (las medidas en mm, desde el costado izquierdo, el frente del cuerpo y el piso interior):

- **Equipos**: medidas, peso y posición de cada cosa que va en el case.
- **Espuma**: bloques que se cortan en capas del espesor de la plancha; cada equipo que cae en un bloque lleva su calado (con holgura) desde la cara abierta hasta el fondo del equipo. Si el fondo cae dentro de una capa, esa capa lleva un rebaje. Sale un DXF por capa (`dxf/espuma/`) y `espuma.csv`; la espuma de la tapa abre hacia el cuerpo.
- **Forma de cada calado** (columnas *Forma en la espuma*, *Radio* y *Dedos* de la tabla de equipos): rectángulo, **redondo** (micrófonos, tachos, focos) o el **contorno de un dibujo** `.dxf` / `.svg` del equipo, que se encaja en su ancho y fondo. Las esquinas se redondean con el radio de la fresa (`espuma_radio`, o uno por equipo) y se pueden agregar **huecos para los dedos** en uno o los dos lados largos (`espuma_dedo_ancho`, `espuma_dedo_largo`). Los calados con forma salen en el DXF de cada capa como polilíneas cerradas (en la capa 0 si son pasantes, en REBAJE si no), en los planos con su dibujo y en la vista 3D y el STEP en escalones; el peso de la espuma descuenta el área real.
- **Cajones** (cases frontales): frente, laterales, trasera y piso con correderas telescópicas (12,7 mm por lado; la corredera más larga que entra si no se indica). Las piezas pasan a la lista de cortes, los DXF y las placas.
- **Rack 19"** (frontal: rieles verticales; vertical: rack de tapa superior): rieles, suplementos si el interior es más ancho, equipos por U, carátulas ciegas para las unidades libres, tuercas enjauladas y tornillos.
- **Chequeos**: piezas que se salen del interior o del cuerpo, choques entre equipos, bandejas, cajones, rieles y espuma, fondo del rack con lugar para cables, perillas contra la tapa, equipos pesados sin soporte trasero, paredes y fondo mínimos de la espuma.

En el paquete, `planos.pdf` suma hojas del interior (vista 3D con las tapas abiertas, la espuma capa por capa con calados y rebajes, el rack de frente con sus U y los frentes de los cajones) y el instructivo suma los pasos de montaje del rack, cada cajón y la espuma.

La pestaña **Interior** resume el espacio útil y el peso, y en la **Vista 3D** la casilla *Ver el interior* abre las tapas. Los parámetros se guardan en el mismo `.scad` (OpenSCAD los ignora).

### Herrajes a mano

La pestaña **Herrajes a mano** muestra cada cara del case en 2D, vista desde afuera y derecha (como queda parado en uso), con los paneles, el aluminio (ángulos, perfiles de cierre, esquineros), la junta de cierre de la tapa y los herrajes automáticos en gris. Ahí se agregan herrajes del catálogo (manijas, cierres, bisagras, topes, pies, ruedas, platos, extras), piezas propias con nombre y medida, y **placas de logo** a partir de un dibujo `.svg` o `.dxf` (remachadas o grabadas). Cada herraje se arrastra con el mouse o se ubica exacto con X/Y (centro, desde el borde izquierdo y desde abajo); se gira, se voltea, se copia, se espeja a la cara opuesta o se reemplaza por otro del catálogo. Al arrastrar, el imán lo pega a la junta de cierre, al borde del aluminio, a los ejes de la cara y a los otros herrajes (Alt lo suelta); las flechas lo mueven de a 1 mm (Mayús: 10 mm). Los cierres y bisagras se centran solos sobre la junta y se marcan en el cuerpo y en la tapa.

Lo que se pone a mano sale en los calados de los paneles y sus DXF (marcas en la capa `MARCA`, logos grabados en `GRABADO`), la lista de herrajes y materiales (con sus remaches), la vista 3D, `planos.pdf` (en azul, con el centro acotado) y un paso del instructivo. Se guarda en el `.scad` como `herrajes_manuales = [[ref, cara, x, y, giro, espejo, ancho, alto, archivo, modo], ...]`; la app avisa si un herraje pisa el aluminio, se sale del panel o choca con otro calado.

Los tests comparan el resultado con OpenSCAD: los datos de 18 proyectos y variantes (`tests/golden/taller`) y las listas y DXF de 3 proyectos (`tests/golden/taller_paquete`). Para regenerarlos: `python tools/generar_golden.py ruta/a/flightcase-generador`.
