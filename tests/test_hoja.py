"""Foto de la vista 3D (copiar / PNG sin fondo) y hoja del case en PDF."""

import pytest

from flightcase.taller.geometria import Opciones3D, malla_3d
from flightcase.taller.modelo import calcular


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _alfa(img, x, y):
    return img.pixelColor(x, y).alpha()


def test_vistas_de_los_lados_a_la_misma_escala(qapp):
    from flightcase.taller.hoja import vistas_lados
    res = calcular({})
    vistas = {v.nombre: v for v in vistas_lados(malla_3d(res, Opciones3D()), px_lado_mayor=200)}
    assert list(vistas) == ["frente", "atras", "izquierda", "derecha", "arriba", "abajo"]
    v = res.valores
    f, d, a = vistas["frente"], vistas["derecha"], vistas["arriba"]
    # las medidas totales incluyen herrajes: nunca menos que el exterior, y poco más
    assert v["ext_ancho"] <= f.ancho < v["ext_ancho"] + 60 and v["ext_alto"] <= f.alto < v["ext_alto"] + 60
    assert v["ext_prof"] <= d.ancho < v["ext_prof"] + 60
    assert a.ancho == pytest.approx(f.ancho) and a.alto == pytest.approx(d.ancho)
    assert vistas["atras"].ancho == pytest.approx(f.ancho)
    for vista in vistas.values():      # la imagen cubre lo que se acota, con la misma escala en todas
        izq, der, abajo, arriba = vista.extent
        assert izq <= vista.limites[0] and der >= vista.limites[1]
        assert abajo <= vista.limites[2] and arriba >= vista.limites[3]
        escala = vista.img.width() / (der - izq)
        assert escala == pytest.approx(200 / max(f.ancho, d.ancho, f.alto), rel=0.03)
        # fondo transparente en la esquina, el case opaco en el medio
        assert _alfa(vista.img, 0, 0) == 0
        assert _alfa(vista.img, vista.img.width() // 2, vista.img.height() // 2) == 255


def test_hoja_del_case_en_pdf(qapp, tmp_path):
    from flightcase.taller.hoja import datos_case, generar_hoja
    res = calcular({})
    ruta = generar_hoja(res, str(tmp_path / "sub" / "hoja.pdf"), "Mi case", px_lado_mayor=160)
    datos = (tmp_path / "sub" / "hoja.pdf").read_bytes()
    assert ruta.endswith("hoja.pdf") and datos.startswith(b"%PDF")
    assert b"/Count 1" in datos                 # una sola hoja
    filas = dict(datos_case(res, malla_3d(res, Opciones3D())))
    assert filas["Exterior (ancho x prof. x alto)"] == "618 x 418 x 348 mm"
    assert filas["Peso aproximado"].endswith("kg")


def test_render_transparente_no_borra_lo_blanco(qapp):
    """Con fondo transparente, una pieza blanca (un rótulo) sigue siendo opaca."""
    from flightcase.taller.render import imagen
    malla = malla_3d(calcular({}), Opciones3D())
    img = imagen(malla, "0,0,0,90,0,0,0", "200,150", {"base": "#ffffff", "lid": "#ffffff", "wall": "#ffffff"},
                 transparente=True, orto=0.25)
    assert _alfa(img, 0, 0) == 0 and _alfa(img, 100, 75) == 255


def test_foto_de_la_vista_3d(qapp, tmp_path):
    """Sin placa de video (como en estos tests) la foto se dibuja por software: igual sale sin fondo."""
    from PySide6.QtWidgets import QApplication
    from flightcase.ui.widgets import TallerWidget
    w = TallerWidget()
    w.vista_3d.resize(320, 240)
    img = w.imagen_3d(True)
    assert not img.isNull() and img.hasAlphaChannel()
    assert _alfa(img, 0, 0) == 0 and _alfa(img, img.width() // 2, img.height() // 2) == 255
    blanca = w.imagen_3d(False)
    assert blanca.pixelColor(0, 0).name() == "#ffffff" and blanca.pixelColor(0, 0).alpha() == 255

    ruta = w.guardar_imagen_3d(str(tmp_path / "vista.png"))
    from PySide6.QtGui import QImage
    assert ruta and _alfa(QImage(ruta), 0, 0) == 0

    assert w.copiar_imagen_3d()
    mime = QApplication.clipboard().mimeData()
    assert mime.hasFormat("image/png") and mime.hasImage()
    QApplication.clipboard().clear()     # con la plataforma offscreen, una imagen en el portapapeles
    #                                      al cerrar Python lo hace caer (segfault al salir)
    assert "foto" in w.barra_3d.botones and w.barra_3d.botones["foto"].menu().actions()


def test_foto_por_opengl_separa_el_fondo(qapp):
    """La foto por OpenGL se saca sobre negro y sobre blanco: de la diferencia sale la transparencia."""
    import numpy as np
    from PySide6.QtGui import QColor, QImage
    from flightcase.ui.widgets.schema_3d_widget import Schema3DCanvas
    c = Schema3DCanvas()
    c.set_mesh(malla_3d(calcular({}), Opciones3D()))

    def falsa(fondo):              # un cuadrado gris medio transparente en el centro
        img = QImage(40, 30, QImage.Format.Format_RGBA8888)
        img.fill(QColor(fondo))
        f = np.frombuffer(img.bits(), dtype=np.uint8).reshape(30, 40, 4)
        bajo = np.array(img.pixelColor(0, 0).getRgb()[:3], dtype=float)
        f[10:20, 10:30, :3] = np.round(0.5 * 200 + 0.5 * bajo).astype(np.uint8)
        f[12:18, 15:25, :3] = 200
        return img
    c._grabar = falsa
    img = c.capturar(True, recortar=False)
    assert img.pixelColor(0, 0).alpha() == 0
    assert img.pixelColor(20, 15).alpha() == 255 and img.pixelColor(20, 15).red() == 200
    assert abs(img.pixelColor(11, 11).alpha() - 128) <= 2 and abs(img.pixelColor(11, 11).red() - 200) <= 3
    recortada = c.capturar(True, recortar=True, margen=2)
    assert (recortada.width(), recortada.height()) == (24, 14)
