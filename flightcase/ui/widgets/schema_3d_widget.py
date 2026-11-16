"""Vista 3D (OpenGL) del Taller."""

from __future__ import annotations
import math

import numpy as np
from typing import Optional, Tuple, List
from PySide6.QtCore import Qt, QPoint, QPointF, QRectF, Signal
from PySide6.QtGui import (
    QPainter,
    QPen,
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QPolygonF,
    QTransform,
    QMouseEvent,
    QWheelEvent,
    QSurfaceFormat,
)
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QScrollArea,
    QLabel,
    QPushButton,
    QSlider,
    QCheckBox,
    QComboBox,
    QFrame,
)
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from OpenGL import GL, GLU

from ...taller.malla import DimensionCallout3D, Point3D, PolygonFace3D, WireframeMesh3D
from ..theme import COLORS, FONDO_3D, REALISTA, REALISTA_METAL


class Schema3DCanvas(QOpenGLWidget):
    """
    Hardware-accelerated OpenGL viewport rendering flightcase 3D geometry with genuine
    Z-buffer depth testing, eliminating sorting artifacts and hidden lines.
    Supports real-time switching between Parallel (Orthographic) and Perspective projections.
    """

    view_changed = Signal()
    medicion_cambiada = Signal(str)    # texto de la medida (vacío = sin medida)
    projection_changed = Signal(bool)  # True = Perspective, False = Parallel

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMinimumSize(150, 150)
        self.setMouseTracking(True)

        # Configure OpenGL surface format for hardware antialiasing (4x MSAA)
        gl_format = QSurfaceFormat()
        gl_format.setSamples(4)
        gl_format.setDepthBufferSize(24)
        self.setFormat(gl_format)

        # Camera & Projection state
        self.azimuth_deg: float = 45.0
        self.elevation_deg: float = 30.0
        self.zoom_factor: float = 1.0
        self.pan_offset_x: float = 0.0
        self.pan_offset_y: float = 0.0
        self.is_perspective: bool = False  # False = Parallel (Ortho), True = Perspective

        # Rendering options
        self.show_dimensions: bool = True
        self.show_inside_walls: bool = True
        self.show_axes: bool = True
        self.fondo_claro: bool = False        # fondo claro (para capturas o pantallas con sol)
        self.mostrar_piso: bool = True        # grilla del piso
        self.realista: bool = True            # colores de case real (placa negra, aluminio)
        self.colores_placa: dict = {}         # color de la placa del proyecto: base, lid, wall
        self.mostrar_cubo: bool = True        # cubo de vistas arriba a la derecha
        self._cubo_caras: List[Tuple[QPolygonF, str]] = []
        # herramienta Medir: clic en dos puntos del case (se engancha al vértice más cercano)
        self.modo_medir: bool = False
        self.medicion: List[Point3D] = []
        self._punto_cerca: Optional[Point3D] = None
        self._matrices: Optional[Tuple[np.ndarray, np.ndarray]] = None   # modelview, proyección
        self._vertices: Optional[np.ndarray] = None

        # Geometry Data
        self.mesh: Optional[WireframeMesh3D] = None

        # Highlight state for selected elements
        self.highlighted_wall_indices: set[int] = set()
        self.highlighted_labels: set[str] = set()

        # Mouse interaction state
        self._last_mouse_pos: Optional[QPoint] = None
        self._mouse_button_down: Optional[Qt.MouseButton] = None
        self.modo_raton: str = "orbitar"      # qué hace el botón izquierdo: orbitar, mover o zoom
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._poner_cursor()

    def set_mesh(self, mesh: WireframeMesh3D) -> None:
        """Sets flightcase 3D mesh and triggers a redraw."""
        self.mesh = mesh
        self._vertices = None
        self.update()

    def set_perspective(self, is_perspective: bool) -> None:
        """Sets projection mode: True for Perspective, False for Parallel (Orthographic)."""
        if self.is_perspective != is_perspective:
            self.is_perspective = is_perspective
            self.update()
            self.projection_changed.emit(self.is_perspective)
            self.view_changed.emit()

    def toggle_projection(self) -> None:
        """Toggles between Parallel (Orthographic) and Perspective rendering."""
        self.set_perspective(not self.is_perspective)

    def reset_view(self, azimuth: float = 45.0, elevation: float = 30.0) -> None:
        """Resets camera orientation to specified angles and re-centers the view."""
        self.azimuth_deg = azimuth
        self.elevation_deg = elevation
        self.zoom_factor = 1.0
        self.pan_offset_x = 0.0
        self.pan_offset_y = 0.0
        self.update()
        self.view_changed.emit()

    def set_view_state(
        self,
        azimuth_deg: float = 45.0,
        elevation_deg: float = 30.0,
        zoom_factor: float = 1.0,
        pan_offset_x: float = 0.0,
        pan_offset_y: float = 0.0,
        is_perspective: bool = False,
        show_dimensions: bool = True,
        show_inside_walls: bool = True,
        show_axes: bool = True,
    ) -> None:
        """Sets full camera transform and visibility states."""
        self.azimuth_deg = float(azimuth_deg)
        self.elevation_deg = float(elevation_deg)
        self.zoom_factor = float(zoom_factor)
        self.pan_offset_x = float(pan_offset_x)
        self.pan_offset_y = float(pan_offset_y)
        self.show_dimensions = bool(show_dimensions)
        self.show_inside_walls = bool(show_inside_walls)
        self.show_axes = bool(show_axes)
        self.set_perspective(bool(is_perspective))
        self.update()
        self.view_changed.emit()

    def set_highlights(
        self,
        wall_indices: Optional[List[int]] = None,
        labels: Optional[List[str]] = None,
    ) -> None:
        """Sets active highlighted wall indices and/or element labels and redraws."""
        self.highlighted_wall_indices = set(wall_indices or [])
        self.highlighted_labels = set(labels or [])
        self.update()
        self.view_changed.emit()

    def clear_highlights(self) -> None:
        """Clears all active highlights."""
        if self.highlighted_wall_indices or self.highlighted_labels:
            self.highlighted_wall_indices.clear()
            self.highlighted_labels.clear()
            self.update()
            self.view_changed.emit()

    def is_face_highlighted(self, face: PolygonFace3D) -> bool:
        """Determines whether a given 3D polygon face is currently selected/highlighted."""
        if not self.highlighted_wall_indices and not self.highlighted_labels:
            return False

        if face.wall_index is not None and face.wall_index in self.highlighted_wall_indices:
            return True

        if not face.label and face.wall_index is None:
            return False

        lbl = face.label or ""
        lbl_lower = lbl.lower()

        for hl in self.highlighted_labels:
            if not hl:
                continue
            if face.label and face.label == hl:
                return True

            hl_lower = hl.lower()

            # 1. Profile selections (from Aluminum Profiles tab)
            is_hl_profile = any(k in hl_lower for k in ("profile", "angle", "mating", "extrusion", "hybrid"))
            is_face_profile = face.color_group == "profile" or "profile" in lbl_lower

            if is_hl_profile:
                if not is_face_profile:
                    continue
                # Highlight matching profile segments
                if "base" in hl_lower or "male" in hl_lower:
                    if "base" in lbl_lower:
                        if ("long" in hl_lower or "front" in hl_lower) and any(s in lbl_lower for s in ("front", "back")):
                            return True
                        if ("short" in hl_lower or "left" in hl_lower) and any(s in lbl_lower for s in ("left", "right")):
                            return True
                        if not any(k in hl_lower for k in ("long", "short", "front", "back", "left", "right")):
                            return True
                elif "lid" in hl_lower or "female" in hl_lower:
                    if "lid" in lbl_lower:
                        if ("long" in hl_lower or "front" in hl_lower) and any(s in lbl_lower for s in ("front", "back")):
                            return True
                        if ("short" in hl_lower or "left" in hl_lower) and any(s in lbl_lower for s in ("left", "right")):
                            return True
                        if not any(k in hl_lower for k in ("long", "short", "front", "back", "left", "right")):
                            return True
                else:
                    return True
                continue

            # If face is a profile but selection is NOT a profile, do not highlight profile
            if is_face_profile:
                continue

            # 2. Inside wall selections (from cut list or wall positions)
            if face.color_group == "wall" or face.wall_index is not None:
                if any(k in hl_lower for k in ("inside walls", "divider", "partition")):
                    return True
                if lbl_lower and (lbl_lower in hl_lower or hl_lower in lbl_lower):
                    return True
                continue

            # 3. Wood panel selections (from Cut List table)
            if face.color_group in ("base", "lid", "endgrain", "uncut_box"):
                # Bottom panel: floor of base box
                if "bottom" in hl_lower and "panel" in hl_lower:
                    if "bottom" in lbl_lower and "panel" in lbl_lower:
                        return True
                    if "top" not in hl_lower:
                        continue

                # Top panel: roof of lid box
                if "top" in hl_lower and "panel" in hl_lower:
                    if "top" in lbl_lower and "panel" in lbl_lower:
                        return True
                    if "bottom" not in hl_lower:
                        continue

                # Long Sides (Front & Back)
                if "long side" in hl_lower or ("front" in hl_lower and "back" in hl_lower):
                    if "base" in hl_lower and "base" not in lbl_lower and "lid" not in hl_lower:
                        continue
                    if "lid" in hl_lower and "lid" not in lbl_lower and "base" not in hl_lower:
                        continue
                    if any(s in lbl_lower for s in ("front", "back")):
                        return True
                    continue

                # Short Sides (Left & Right)
                if "short side" in hl_lower or ("left" in hl_lower and "right" in hl_lower):
                    if "base" in hl_lower and "base" not in lbl_lower and "lid" not in hl_lower:
                        continue
                    if "lid" in hl_lower and "lid" not in lbl_lower and "base" not in hl_lower:
                        continue
                    if any(s in lbl_lower for s in ("left", "right")):
                        return True
                    continue

                # Direct substring match as fallback for custom panel labels
                if lbl_lower and (lbl_lower in hl_lower or hl_lower in lbl_lower):
                    return True

        return False


    # --- Navegación (botones, teclado y mouse) ---

    ZOOM_MIN, ZOOM_MAX = 0.05, 40.0
    VISTAS = {   # nombre: (azimut, elevación). Azimut 0 mira el frente (y = 0), 90 el lado derecho.
        "iso": (45.0, 30.0), "frente": (0.0, 0.0), "atras": (180.0, 0.0), "izquierda": (270.0, 0.0),
        "derecha": (90.0, 0.0), "arriba": (0.0, 89.9), "abajo": (0.0, -89.9),
    }

    def _cambio(self) -> None:
        self.update()
        self.view_changed.emit()

    def set_modo_raton(self, modo: str) -> None:
        if modo in ("orbitar", "mover", "zoom") and modo != self.modo_raton:
            self.modo_raton = modo
            self._poner_cursor()
            self.view_changed.emit()

    def _poner_cursor(self, arrastrando: bool = False) -> None:
        if getattr(self, "modo_medir", False) and not arrastrando:
            forma = Qt.CursorShape.CrossCursor
        elif self.modo_raton == "mover":
            forma = Qt.CursorShape.ClosedHandCursor if arrastrando else Qt.CursorShape.OpenHandCursor
        elif self.modo_raton == "zoom":
            forma = Qt.CursorShape.SizeVerCursor
        else:
            forma = Qt.CursorShape.SizeAllCursor if arrastrando else Qt.CursorShape.ArrowCursor
        self.setCursor(forma)

    def zoom(self, factor: float, centro: Optional[QPointF] = None) -> None:
        """Acerca (factor > 1) o aleja, manteniendo quieto el punto de la pantalla `centro`."""
        nuevo = max(self.ZOOM_MIN, min(self.ZOOM_MAX, self.zoom_factor * factor))
        f = nuevo / self.zoom_factor
        if centro is not None:
            sx = centro.x() - self.width() / 2.0
            sy = centro.y() - self.height() / 2.0
            self.pan_offset_x = sx - (sx - self.pan_offset_x) * f
            self.pan_offset_y = sy - (sy - self.pan_offset_y) * f
        else:
            self.pan_offset_x *= f
            self.pan_offset_y *= f
        self.zoom_factor = nuevo
        self._cambio()

    def acercar(self) -> None:
        self.zoom(1.25)

    def alejar(self) -> None:
        self.zoom(1 / 1.25)

    def mover(self, dx: float, dy: float) -> None:
        self.pan_offset_x += dx
        self.pan_offset_y += dy
        self._cambio()

    def girar(self, d_azimut: float, d_elevacion: float = 0.0) -> None:
        self.azimuth_deg = (self.azimuth_deg + d_azimut) % 360.0
        self.elevation_deg = max(-89.9, min(89.9, self.elevation_deg + d_elevacion))
        self._cambio()

    def encuadrar(self) -> None:
        """Todo el case centrado y entero en la ventana, sin cambiar el ángulo."""
        self.zoom_factor = 1.0
        self.pan_offset_x = self.pan_offset_y = 0.0
        self._cambio()

    def set_vista(self, nombre: str) -> None:
        self.azimuth_deg, self.elevation_deg = self.VISTAS[nombre]
        self.encuadrar()

    def set_mostrar_cotas(self, si: bool) -> None:
        self.show_dimensions = bool(si)
        self._cambio()

    def set_mostrar_ejes(self, si: bool) -> None:
        self.show_axes = bool(si)
        self._cambio()

    # --- Medir ---

    RADIO_ENGANCHE = 14.0     # píxeles

    def set_modo_medir(self, si: bool) -> None:
        self.modo_medir = bool(si)
        self._punto_cerca = None
        if not si:
            self.borrar_medicion()
        self._poner_cursor()
        self.update()

    def borrar_medicion(self) -> None:
        if self.medicion:
            self.medicion = []
            self.medicion_cambiada.emit("")
            self.update()

    @staticmethod
    def texto_medida(a: Point3D, b: Point3D) -> str:
        fmt = lambda v: f"{v:.1f}".rstrip("0").rstrip(".").replace(".", ",")
        dx, dy, dz = abs(b.x - a.x), abs(b.y - a.y), abs(b.z - a.z)
        d = math.sqrt(dx * dx + dy * dy + dz * dz)
        return f"{fmt(d)} mm  (Δx {fmt(dx)} · Δy {fmt(dy)} · Δz {fmt(dz)})"

    def _proyectar_np(self, pts: np.ndarray) -> Optional[np.ndarray]:
        """(x, y en píxeles, profundidad) de cada punto, con las matrices del último cuadro."""
        if self._matrices is None or len(pts) == 0:
            return None
        mv, pr = self._matrices
        h4 = np.hstack([pts, np.ones((len(pts), 1))]) @ mv @ pr
        w = np.where(np.abs(h4[:, 3]) < 1e-12, 1e-12, h4[:, 3])
        ndc = h4[:, :3] / w[:, None]
        W, H = max(1, self.width()), max(1, self.height())
        return np.column_stack([(ndc[:, 0] + 1) / 2 * W, H - (ndc[:, 1] + 1) / 2 * H, ndc[:, 2]])

    def punto_cercano(self, pos: QPointF) -> Optional[Point3D]:
        """El vértice del case más cercano al mouse (y de esos, el de más adelante)."""
        if self.mesh is None:
            return None
        if self._vertices is None:
            pts = {(p.x, p.y, p.z) for f in self.mesh.faces for p in f.vertices}
            self._vertices = np.array(sorted(pts), dtype=float).reshape(-1, 3)
        pr = self._proyectar_np(self._vertices)
        if pr is None:
            return None
        d = np.hypot(pr[:, 0] - pos.x(), pr[:, 1] - pos.y())
        cerca = np.nonzero(d <= self.RADIO_ENGANCHE)[0]
        if len(cerca) == 0:
            return None
        i = cerca[np.argmin(pr[cerca, 2] + d[cerca] * 1e-4)]
        x, y, z = self._vertices[i]
        return Point3D(float(x), float(y), float(z))

    def _clic_medir(self, pos: QPointF) -> bool:
        pt = self.punto_cercano(pos)
        if pt is None:
            return False
        if len(self.medicion) >= 2:
            self.medicion = []
        self.medicion.append(pt)
        texto = self.texto_medida(*self.medicion) if len(self.medicion) == 2 else ""
        self.medicion_cambiada.emit(texto)
        self.update()
        return True

    def _dibujar_medicion(self, painter: QPainter) -> None:
        if not self.modo_medir:
            return
        pts = list(self.medicion) + ([self._punto_cerca] if self._punto_cerca is not None else [])
        if not pts:
            return
        pr = self._proyectar_np(np.array([(p.x, p.y, p.z) for p in pts], dtype=float))
        if pr is None:
            return
        color = QColor("#22d3ee")
        scr = [QPointF(float(x), float(y)) for x, y, _ in pr]
        n = len(self.medicion)
        if n == 2:
            painter.setPen(QPen(color, 2.0))
            painter.drawLine(scr[0], scr[1])
            texto = self.texto_medida(*self.medicion)
            mid = QPointF((scr[0].x() + scr[1].x()) / 2, (scr[0].y() + scr[1].y()) / 2)
            f = QFont("Segoe UI", 10, QFont.Weight.Bold)
            painter.setFont(f)
            r = QFontMetrics(f).boundingRect(texto)
            caja = QRectF(mid.x() - r.width() / 2 - 7, mid.y() - r.height() - 12, r.width() + 14, r.height() + 6)
            painter.setBrush(QBrush(QColor(8, 20, 32, 235)))
            painter.drawRoundedRect(caja, 4, 4)
            painter.setPen(QColor("#a5f3fc"))
            painter.drawText(caja, Qt.AlignmentFlag.AlignCenter, texto)
        elif n == 1 and self._punto_cerca is not None:
            painter.setPen(QPen(color, 1.4, Qt.PenStyle.DashLine))
            painter.drawLine(scr[0], scr[-1])
        painter.setBrush(QBrush(color))
        for i, q in enumerate(scr):
            enganche = self._punto_cerca is not None and i == len(scr) - 1
            painter.setPen(QPen(QColor("#0b1120"), 1.2))
            painter.drawEllipse(q, 6.0 if enganche else 4.5, 6.0 if enganche else 4.5)

    def set_fondo_claro(self, si: bool) -> None:
        self.fondo_claro = bool(si)
        self._cambio()

    def set_mostrar_piso(self, si: bool) -> None:
        self.mostrar_piso = bool(si)
        self._cambio()

    def set_realista(self, si: bool) -> None:
        self.realista = bool(si)
        self._cambio()

    def set_colores_placa(self, colores: dict) -> None:
        self.colores_placa = dict(colores or {})
        self.update()

    # --- Cubo de vistas (arriba a la derecha: clic en una cara = esa vista) ---

    CUBO_LADO = 64.0
    CUBO_ROTULOS = {(0, -1, 0): "FRENTE", (0, 1, 0): "ATRÁS", (1, 0, 0): "DERECHA", (-1, 0, 0): "IZQUIERDA",
                    (0, 0, 1): "ARRIBA", (0, 0, -1): "ABAJO"}
    CUBO_VISTAS = {(0, -1, 0): "frente", (0, 1, 0): "atras", (1, 0, 0): "derecha", (-1, 0, 0): "izquierda",
                   (0, 0, 1): "arriba", (0, 0, -1): "abajo"}

    def proyectar_direccion(self, x: float, y: float, z: float) -> Tuple[float, float, float]:
        """(derecha, abajo, hacia el que mira) en pantalla de una dirección del mundo, con la
        misma rotación que la cámara de OpenGL (elevación sobre X, azimut sobre Z)."""
        az, el = math.radians(self.azimuth_deg), math.radians(self.elevation_deg)
        x1 = x * math.cos(az) + y * math.sin(az)
        y1 = -x * math.sin(az) + y * math.cos(az)
        y2 = y1 * math.sin(el) + z * math.cos(el)
        prof = -y1 * math.cos(el) + z * math.sin(el)
        return x1, -y2, prof

    def centro_cubo(self) -> QPointF:
        return QPointF(self.width() - 78.0, 78.0)

    def _armar_cubo(self) -> List[Tuple[QPolygonF, str, Tuple[int, int, int], float]]:
        c, L = self.centro_cubo(), self.CUBO_LADO
        caras = []
        for n in self.CUBO_ROTULOS:
            _, _, prof = self.proyectar_direccion(*n)
            if prof <= 0.02:
                continue
            i = [k for k in range(3) if n[k]][0]
            u = [0.0, 0.0, 0.0]
            v = [0.0, 0.0, 0.0]
            u[(i + 1) % 3] = 1.0
            v[(i + 2) % 3] = 1.0
            pts = []
            for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                q = [n[k] + a * u[k] + b * v[k] for k in range(3)]
                sx, sy, _ = self.proyectar_direccion(*q)
                pts.append(QPointF(c.x() + sx * L / 2, c.y() + sy * L / 2))
            caras.append((QPolygonF(pts), self.CUBO_VISTAS[n], n, prof))
        caras.sort(key=lambda t: t[3])
        return caras

    def vista_en_cubo(self, pos: QPointF) -> Optional[str]:
        """La vista de la cara del cubo bajo el punto (o None)."""
        if not self.mostrar_cubo:
            return None
        for poly, vista, _, _ in reversed(self._armar_cubo()):
            if poly.containsPoint(pos, Qt.FillRule.OddEvenFill):
                return vista
        return None

    # dirección «derecha» y «arriba» del texto sobre cada cara, mirándola desde afuera
    CUBO_TEXTO = {(0, -1, 0): ((1, 0, 0), (0, 0, 1)), (0, 1, 0): ((-1, 0, 0), (0, 0, 1)),
                  (1, 0, 0): ((0, 1, 0), (0, 0, 1)), (-1, 0, 0): ((0, -1, 0), (0, 0, 1)),
                  (0, 0, 1): ((1, 0, 0), (0, 1, 0)), (0, 0, -1): ((1, 0, 0), (0, -1, 0))}

    def transformacion_cara(self, n: Tuple[int, int, int]) -> QTransform:
        """Lleva el cuadrado (-50..50, -50..50) de la cara `n` del cubo a la pantalla, en
        perspectiva: así el rótulo queda pegado a la cara y gira con el cubo."""
        c, k = self.centro_cubo(), self.CUBO_LADO / 2 / 50.0
        der, arriba = self.CUBO_TEXTO[n]
        rx, ry, _ = self.proyectar_direccion(*der)
        ux, uy, _ = self.proyectar_direccion(*arriba)
        nx, ny, _ = self.proyectar_direccion(*n)
        return QTransform(rx * k, ry * k, -ux * k, -uy * k,
                          c.x() + nx * self.CUBO_LADO / 2, c.y() + ny * self.CUBO_LADO / 2)

    def _dibujar_cubo(self, painter: QPainter) -> None:
        claro = self.fondo_claro
        for poly, vista, n, prof in self._armar_cubo():
            tono = int(60 + 70 * prof) if not claro else int(235 - 40 * (1 - prof))
            relleno = QColor(tono // 2 + 10, tono // 2 + 22, tono + 20) if not claro else QColor(tono, tono, tono + 8)
            painter.setBrush(QBrush(relleno))
            painter.setPen(QPen(QColor("#93a4c3") if not claro else QColor("#7b8494"), 1.2))
            painter.drawPolygon(poly)
            if prof > 0.12:
                painter.save()
                painter.setTransform(self.transformacion_cara(n), True)
                texto = self.CUBO_ROTULOS[n]
                f = QFont("Segoe UI")
                f.setPixelSize(int(min(25, 140 / len(texto))))
                f.setBold(True)
                painter.setFont(f)
                col = QColor("#e6ecf7") if not claro else QColor("#2b3240")
                col.setAlphaF(min(1.0, 0.35 + prof))
                painter.setPen(col)
                painter.drawText(QRectF(-50, -50, 100, 100), Qt.AlignmentFlag.AlignCenter, texto)
                painter.restore()

    def keyPressEvent(self, event) -> None:
        k, mods = event.key(), event.modifiers()
        paso = 40.0 if mods & Qt.KeyboardModifier.ShiftModifier else 0.0
        flechas = {Qt.Key.Key_Left: (-1, 0), Qt.Key.Key_Right: (1, 0), Qt.Key.Key_Up: (0, -1), Qt.Key.Key_Down: (0, 1)}
        if k in flechas:
            dx, dy = flechas[k]
            if paso:
                self.mover(dx * paso, dy * paso)          # Mayús + flechas: mover
            else:
                self.girar(-dx * 5.0, -dy * 5.0)          # flechas: girar de a 5°
        elif k in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self.acercar()
        elif k in (Qt.Key.Key_Minus, Qt.Key.Key_Underscore):
            self.alejar()
        elif k == Qt.Key.Key_Escape and self.modo_medir:
            self.borrar_medicion()
        elif k in (Qt.Key.Key_Home, Qt.Key.Key_F):
            self.encuadrar()
        else:
            super().keyPressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        self.encuadrar()

    # --- Mouse Event Handlers ---

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            vista = self.vista_en_cubo(event.position())
            if vista:
                self.set_vista(vista)
                return
            if self.modo_medir and self._clic_medir(event.position()):
                return
        self._last_mouse_pos = event.position().toPoint()
        self._mouse_button_down = event.button()
        self._poner_cursor(arrastrando=True)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        curr_pos = event.position().toPoint()
        if self.modo_medir and self._mouse_button_down is None:
            cerca = self.punto_cercano(event.position())
            if cerca != self._punto_cerca:
                self._punto_cerca = cerca
                self.update()
        if self._last_mouse_pos is None or self._mouse_button_down is None:
            return
        delta = curr_pos - self._last_mouse_pos
        self._last_mouse_pos = curr_pos
        boton = self._mouse_button_down
        if boton == Qt.MouseButton.LeftButton:
            accion = self.modo_raton
        elif boton in (Qt.MouseButton.RightButton, Qt.MouseButton.MiddleButton):
            accion = "mover"          # botón derecho o rueda apretada: mover siempre
        else:
            return
        if accion == "orbitar":
            self.girar(-delta.x() * 0.5, delta.y() * 0.5)
        elif accion == "mover":
            self.mover(delta.x(), delta.y())
        else:
            self.zoom(1.01 ** (-delta.y()))

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._last_mouse_pos = None
        self._mouse_button_down = None
        self._poner_cursor()

    def wheelEvent(self, event: QWheelEvent) -> None:
        pasos = event.angleDelta().y() / 120.0
        if pasos:
            self.zoom(1.15 ** pasos, event.position())   # acerca hacia donde está el mouse

    # --- OpenGL Pipeline Implementation ---

    def initializeGL(self) -> None:
        """Configures initial OpenGL rendering state."""
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glDepthFunc(GL.GL_LEQUAL)
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)
        GL.glEnable(GL.GL_MULTISAMPLE)
        GL.glEnable(GL.GL_LINE_SMOOTH)
        GL.glHint(GL.GL_LINE_SMOOTH_HINT, GL.GL_NICEST)
        GL.glEnable(GL.GL_POLYGON_OFFSET_FILL)
        GL.glPolygonOffset(1.2, 1.2)

        bg = QColor(COLORS.get("bg_schema", "#141419"))
        GL.glClearColor(bg.redF(), bg.greenF(), bg.blueF(), 1.0)

    def resizeGL(self, w: int, h: int) -> None:
        """Updates OpenGL viewport when widget is resized."""
        dpr = self.devicePixelRatioF()      # pantallas Retina / con escala: el buffer tiene más píxeles
        GL.glViewport(0, 0, max(1, round(w * dpr)), max(1, round(h * dpr)))

    def paintGL(self) -> None:
        """Executes full 3D OpenGL pass with depth testing and 2D QPainter overlay."""
        w, h = max(1, self.width()), max(1, self.height())
        aspect = w / h

        # 1. Clear color and depth buffers, con un degradado de fondo
        arriba, abajo = (QColor(c) for c in FONDO_3D["claro" if self.fondo_claro else "oscuro"])
        GL.glClearColor(abajo.redF(), abajo.greenF(), abajo.blueF(), 1.0)
        dpr = self.devicePixelRatioF()      # en Retina el buffer es 2x: si no, el 3D ocupa un cuarto
        GL.glViewport(0, 0, max(1, round(w * dpr)), max(1, round(h * dpr)))
        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
        self._dibujar_degradado(arriba, abajo)

        if not self.mesh:
            painter = QPainter(self)
            painter.setPen(QColor("#7a7a90"))
            painter.setFont(QFont("Segoe UI", 11))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No hay geometría de flightcase para mostrar")
            painter.end()
            return

        # 2. Compute 3D bounding box & center
        p_min, p_max = self.mesh.bounding_box
        center = Point3D(
            (p_min.x + p_max.x) / 2.0,
            (p_min.y + p_max.y) / 2.0,
            (p_min.z + p_max.z) / 2.0,
        )
        diag = math.sqrt((p_max.x - p_min.x)**2 + (p_max.y - p_min.y)**2 + (p_max.z - p_min.z)**2)
        max_dim = max(100.0, diag)

        # 3. Setup Projection Matrix
        GL.glMatrixMode(GL.GL_PROJECTION)
        GL.glLoadIdentity()
        fov_y = 38.0

        ortho_half_h = (max_dim * 0.72) / self.zoom_factor
        ortho_half_w = ortho_half_h * aspect
        if aspect < 1.0:
            ortho_half_w = (max_dim * 0.72) / self.zoom_factor
            ortho_half_h = ortho_half_w / aspect

        if self.is_perspective:
            z_near = max(1.0, max_dim * 0.02)
            z_far = max_dim * 25.0
            GLU.gluPerspective(fov_y, aspect, z_near, z_far)
        else:
            GL.glOrtho(-ortho_half_w, ortho_half_w, -ortho_half_h, ortho_half_h, -max_dim * 10.0, max_dim * 10.0)

        # 4. Setup ModelView Matrix
        GL.glMatrixMode(GL.GL_MODELVIEW)
        GL.glLoadIdentity()

        if self.is_perspective:
            cam_dist = (max_dim * 1.7) / self.zoom_factor
            pan_scale = (cam_dist * math.tan(math.radians(fov_y / 2.0))) / (h / 2.0)
            GL.glTranslatef(self.pan_offset_x * pan_scale, -self.pan_offset_y * pan_scale, -cam_dist)
        else:
            pan_scale = (2.0 * ortho_half_h) / h
            GL.glTranslatef(self.pan_offset_x * pan_scale, -self.pan_offset_y * pan_scale, 0.0)

        # Camera rotation (Elevation around X, Azimuth around Z)
        GL.glRotatef(self.elevation_deg - 90.0, 1.0, 0.0, 0.0)
        GL.glRotatef(-self.azimuth_deg, 0.0, 0.0, 1.0)
        # Center flightcase at origin
        GL.glTranslatef(-center.x, -center.y, -center.z)

        # 5. Render 3D Scene into Hardware Z-Buffer
        GL.glEnable(GL.GL_DEPTH_TEST)

        # 5a. Ground Reference Grid
        if self.mostrar_piso:
            self._draw_gl_ground_grid(p_max)

        # 5b. Solid Panel Polygons with Directional Lighting & Offset
        if self.mesh.faces:
            self._draw_gl_solid_faces()
            self._draw_gl_face_outlines()
            self._draw_gl_dashed_segments()
        else:
            self._draw_gl_fallback_segments()

        # 6. Capture GL Transformation Matrices for 2D Coordinate Unprojecting
        mv_matrix = GL.glGetDoublev(GL.GL_MODELVIEW_MATRIX)
        proj_matrix = GL.glGetDoublev(GL.GL_PROJECTION_MATRIX)
        self._matrices = (np.array(mv_matrix, dtype=float).reshape(4, 4),
                          np.array(proj_matrix, dtype=float).reshape(4, 4))
        viewport = (0, 0, w, h)       # las cotas y los ejes se dibujan en píxeles lógicos (QPainter)

        def project_3d_to_screen(p: Point3D) -> QPointF:
            wx, wy, wz = GLU.gluProject(p.x, p.y, p.z, mv_matrix, proj_matrix, viewport)
            return QPointF(wx, h - wy)

        # 7. Render 2D Overlays (Crisp High-DPI Dimensions, Coordinate Axes & HUD)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        # 7a. Dimension Callouts
        if self.show_dimensions:
            for dim in self.mesh.dimensions:
                self._draw_2d_dimension_callout(painter, dim, project_3d_to_screen)

        # 7b. 3D Coordinate Axis Triad (Bottom-Left)
        if self.show_axes:
            self._draw_axis_triad(painter)

        # 7c. HUD Status & Info (Top-Left)
        self._draw_hud(painter)

        # 7c'. Medición (herramienta Medir)
        self._dibujar_medicion(painter)

        # 7d. Cubo de vistas (arriba a la derecha)
        if self.mostrar_cubo:
            self._dibujar_cubo(painter)

        painter.end()

    # --- 3D OpenGL Rendering Helpers ---

    def _dibujar_degradado(self, arriba: QColor, abajo: QColor) -> None:
        GL.glMatrixMode(GL.GL_PROJECTION)
        GL.glLoadIdentity()
        GL.glMatrixMode(GL.GL_MODELVIEW)
        GL.glLoadIdentity()
        GL.glDisable(GL.GL_DEPTH_TEST)
        GL.glBegin(GL.GL_QUADS)
        GL.glColor4f(abajo.redF(), abajo.greenF(), abajo.blueF(), 1.0)
        GL.glVertex2f(-1.0, -1.0)
        GL.glVertex2f(1.0, -1.0)
        GL.glColor4f(arriba.redF(), arriba.greenF(), arriba.blueF(), 1.0)
        GL.glVertex2f(1.0, 1.0)
        GL.glVertex2f(-1.0, 1.0)
        GL.glEnd()
        GL.glEnable(GL.GL_DEPTH_TEST)

    def _draw_gl_ground_grid(self, p_max: Point3D) -> None:
        """Renders ground reference grid in the Z = 0 ground plane."""
        span_x = max(200.0, p_max.x * 1.3)
        span_y = max(200.0, p_max.y * 1.3)
        step = 100.0

        grid_c = QColor(FONDO_3D["grilla_clara"] if self.fondo_claro else FONDO_3D["grilla"])
        GL.glColor4f(grid_c.redF(), grid_c.greenF(), grid_c.blueF(), 0.5)
        GL.glLineWidth(1.0)
        GL.glBegin(GL.GL_LINES)

        x = -50.0
        while x <= span_x + step:
            GL.glVertex3f(x, -50.0, 0.0)
            GL.glVertex3f(x, span_y, 0.0)
            x += step

        y = -50.0
        while y <= span_y + step:
            GL.glVertex3f(-50.0, y, 0.0)
            GL.glVertex3f(span_x, y, 0.0)
            y += step

        GL.glEnd()

    def _draw_gl_solid_faces(self) -> None:
        """Renders filled 3D panel faces into OpenGL Z-buffer with directional lighting."""
        if not self.mesh or not self.mesh.faces:
            return

        GL.glEnable(GL.GL_POLYGON_OFFSET_FILL)
        GL.glPolygonOffset(1.2, 1.2)

        # Key directional light in world space
        lx, ly, lz = 0.55, -0.45, 0.70
        l_len = math.sqrt(lx*lx + ly*ly + lz*lz)
        lx, ly, lz = lx / l_len, ly / l_len, lz / l_len

        for face in self.mesh.faces:
            if face.color_group == "wall" and not self.show_inside_walls:
                continue

            nx, ny, nz = face.normal
            diff = max(0.0, nx * lx + ny * ly + nz * lz)
            shade = 0.50 + diff * 0.50

            fill_color, _, _ = self._get_face_styling(face, shade)
            GL.glColor4f(fill_color.redF(), fill_color.greenF(), fill_color.blueF(), 1.0)

            GL.glBegin(GL.GL_POLYGON)
            for v in face.vertices:
                GL.glVertex3f(v.x, v.y, v.z)
            GL.glEnd()

    def _draw_gl_face_outlines(self) -> None:
        """Renders crisp boundary outlines on solid panel faces with depth testing."""
        if not self.mesh or not self.mesh.faces:
            return

        GL.glDisable(GL.GL_POLYGON_OFFSET_FILL)

        for face in self.mesh.faces:
            if face.color_group == "wall" and not self.show_inside_walls:
                continue

            _, edge_color, line_width = self._get_face_styling(face, 1.0)
            GL.glLineWidth(float(line_width))
            GL.glColor4f(edge_color.redF(), edge_color.greenF(), edge_color.blueF(), 1.0)

            GL.glBegin(GL.GL_LINE_LOOP)
            for v in face.vertices:
                GL.glVertex3f(v.x, v.y, v.z)
            GL.glEnd()

    def _draw_gl_dashed_segments(self) -> None:
        """Renders dashed markings (e.g. lid cut lines on uncut panels) with depth testing."""
        if not self.mesh or not self.mesh.segments:
            return

        dashed_segs = [s for s in self.mesh.segments if s.style == "dashed"]
        if not dashed_segs:
            return

        GL.glEnable(GL.GL_LINE_STIPPLE)
        GL.glLineStipple(3, 0xAAAA)
        GL.glLineWidth(2.5)

        for seg in dashed_segs:
            if seg.color_group == "wall" and not self.show_inside_walls:
                continue

            color_hex = COLORS.get("cut_line", COLORS.get("profile_edge", "#f59e0b"))
            edge_color = QColor(color_hex)
            GL.glColor4f(edge_color.redF(), edge_color.greenF(), edge_color.blueF(), 1.0)

            GL.glBegin(GL.GL_LINES)
            GL.glVertex3f(seg.p1.x, seg.p1.y, seg.p1.z)
            GL.glVertex3f(seg.p2.x, seg.p2.y, seg.p2.z)
            GL.glEnd()

        GL.glDisable(GL.GL_LINE_STIPPLE)

    def _draw_gl_fallback_segments(self) -> None:
        """Fallback line renderer if no solid faces exist."""
        if not self.mesh or not self.mesh.segments:
            return

        for seg in self.mesh.segments:
            if seg.color_group == "wall" and not self.show_inside_walls:
                continue

            edge_color = QColor(COLORS.get(f"{seg.color_group}_edge", COLORS["base_edge"]))
            GL.glLineWidth(2.0)
            GL.glColor4f(edge_color.redF(), edge_color.greenF(), edge_color.blueF(), 1.0)

            GL.glBegin(GL.GL_LINES)
            GL.glVertex3f(seg.p1.x, seg.p1.y, seg.p1.z)
            GL.glVertex3f(seg.p2.x, seg.p2.y, seg.p2.z)
            GL.glEnd()

    def _get_face_styling(self, face: PolygonFace3D, shade: float = 1.0) -> Tuple[QColor, QColor, float]:
        """Calculates shaded 100% opaque fill color, edge color, and line width for a 3D panel face."""
        is_highlighted = self.is_face_highlighted(face)

        if is_highlighted:
            if face.is_endgrain:
                base_fill_hex = COLORS.get("highlight_endgrain_fill", "#f59e0b")
                base_edge_hex = COLORS.get("highlight_endgrain_edge", "#fef08a")
                line_width = 3.2
            else:
                base_fill_hex = COLORS.get("highlight_fill", "#d97706")
                base_edge_hex = COLORS.get("highlight_edge", "#fde047")
                line_width = 3.0

            raw_color = QColor(base_fill_hex)
            lit_shade = 0.65 + shade * 0.35
            r = max(0, min(255, int(raw_color.red() * lit_shade)))
            g = max(0, min(255, int(raw_color.green() * lit_shade)))
            b = max(0, min(255, int(raw_color.blue() * lit_shade)))
            fill_color = QColor(r, g, b, 255)
            edge_color = QColor(base_edge_hex)
            return fill_color, edge_color, line_width

        if self.realista:
            return self._estilo_realista(face, shade)
        base_fill_hex = COLORS.get(f"{face.color_group}_fill", COLORS["base_fill"])
        base_edge_hex = COLORS.get(f"{face.color_group}_edge", COLORS["base_edge"])
        line_width = 1.6

        if face.is_endgrain:
            base_fill_hex = COLORS.get("endgrain_fill", "#334155")
            base_edge_hex = COLORS.get("endgrain_edge", "#60a5fa")
            line_width = 2.0
        elif face.color_group == "profile":
            line_width = 2.0
        elif face.color_group == "wall":
            line_width = 1.8

        raw_color = QColor(base_fill_hex)
        r = max(0, min(255, int(raw_color.red() * shade)))
        g = max(0, min(255, int(raw_color.green() * shade)))
        b = max(0, min(255, int(raw_color.blue() * shade)))
        fill_color = QColor(r, g, b, 255)  # 100% opaque solid color

        edge_color = QColor(base_edge_hex)
        return fill_color, edge_color, line_width

    def _estilo_realista(self, face: PolygonFace3D, shade: float) -> Tuple[QColor, QColor, float]:
        """Colores de un case de verdad: placa (negra si el proyecto no dice otra), aluminio y
        herrajes cromados. Las aristas van finas y oscuras para que se lea la forma."""
        grupo = face.color_group
        relleno, borde = REALISTA.get(grupo, REALISTA["herraje"])
        if grupo in self.colores_placa and QColor(self.colores_placa[grupo]).lightness() > 40:
            relleno = self.colores_placa[grupo]          # placa de color (las negras usan el negro de acá)
            borde = QColor(relleno).darker(260).name()
        if face.is_endgrain and grupo in ("base", "lid"):
            relleno = QColor(relleno).darker(115).name() if relleno != REALISTA[grupo][0] else REALISTA["canto"][0]
        c = QColor(relleno)
        brillo = 0.35 + 0.75 * shade if grupo in REALISTA_METAL else 0.55 + 0.55 * shade
        fill = QColor(max(0, min(255, int(c.red() * brillo))), max(0, min(255, int(c.green() * brillo))),
                      max(0, min(255, int(c.blue() * brillo))))
        return fill, QColor(borde), 1.0

    # --- 2D Vector Overlay Helpers ---

    def _draw_2d_dimension_callout(
        self,
        painter: QPainter,
        dim: DimensionCallout3D,
        project_func,
    ) -> None:
        """Renders crisp vector dimension line, witness extension lines, ticks, and text badge."""
        p1 = dim.start
        p2 = dim.end
        ox, oy, oz = dim.offset_vector

        p1_off = Point3D(p1.x + ox, p1.y + oy, p1.z + oz)
        p2_off = Point3D(p2.x + ox, p2.y + oy, p2.z + oz)

        p1_s = project_func(p1)
        p2_s = project_func(p2)
        p1_off_s = project_func(p1_off)
        p2_off_s = project_func(p2_off)

        # Witness Extension Lines
        witness_pen = QPen(QColor("#64748b"), 1.0, Qt.PenStyle.DotLine)
        painter.setPen(witness_pen)
        painter.drawLine(p1_s, p1_off_s)
        painter.drawLine(p2_s, p2_off_s)

        # Dimension Line
        dim_pen = QPen(QColor(COLORS.get("dim_line", "#f59e0b")), 1.5, Qt.PenStyle.SolidLine)
        painter.setPen(dim_pen)
        painter.drawLine(p1_off_s, p2_off_s)

        # End Ticks / Arrows
        self._draw_arrow_tick(painter, p1_off_s, p2_off_s)
        self._draw_arrow_tick(painter, p2_off_s, p1_off_s)

        # Text Label Badge
        mid_s = QPointF((p1_off_s.x() + p2_off_s.x()) / 2.0, (p1_off_s.y() + p2_off_s.y()) / 2.0)
        font = QFont("Segoe UI", 10, QFont.Weight.Bold)
        painter.setFont(font)
        fm = QFontMetrics(font)
        dim_text = dim.label
        text_rect = fm.boundingRect(dim_text)

        padding_x = 6
        padding_y = 3
        badge_w = text_rect.width() + padding_x * 2
        badge_h = text_rect.height() + padding_y * 2
        badge_rect = QRectF(mid_s.x() - badge_w / 2.0, mid_s.y() - badge_h / 2.0, badge_w, badge_h)

        # Badge pill background
        painter.setBrush(QBrush(QColor(24, 24, 32, 230)))
        painter.setPen(QPen(QColor(COLORS.get("dim_line", "#f59e0b")), 1.2))
        painter.drawRoundedRect(badge_rect, 4, 4)

        # Text string
        painter.setPen(QColor(COLORS.get("dim_text", "#fbbf24")))
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, dim_text)

    def _draw_arrow_tick(self, painter: QPainter, pt: QPointF, towards_pt: QPointF) -> None:
        """Draws small dimension arrow or tick marker at terminal point."""
        dx = towards_pt.x() - pt.x()
        dy = towards_pt.y() - pt.y()
        length = math.sqrt(dx * dx + dy * dy)
        if length < 1e-4:
            return

        ux, uy = dx / length, dy / length
        arrow_size = 7.0
        angle = math.radians(25.0)

        cos_a = math.cos(angle)
        sin_a = math.sin(angle)

        v1_x = (ux * cos_a - uy * sin_a) * arrow_size
        v1_y = (ux * sin_a + uy * cos_a) * arrow_size
        v2_x = (ux * cos_a + uy * sin_a) * arrow_size
        v2_y = (-ux * sin_a + uy * cos_a) * arrow_size

        arrow_p1 = QPointF(pt.x() + v1_x, pt.y() + v1_y)
        arrow_p2 = QPointF(pt.x() + v2_x, pt.y() + v2_y)

        poly = QPolygonF([pt, arrow_p1, arrow_p2])
        painter.setBrush(QBrush(QColor(COLORS.get("dim_line", "#f59e0b"))))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPolygon(poly)

    def _draw_axis_triad(self, painter: QPainter) -> None:
        """Draws rotating 3D coordinate axis indicator in the bottom-left corner."""
        origin_s = QPointF(50.0, self.height() - 50.0)
        axis_len = 32.0

        rad_az = math.radians(self.azimuth_deg)
        rad_el = math.radians(self.elevation_deg)
        sin_az, cos_az = math.sin(rad_az), math.cos(rad_az)
        sin_el, cos_el = math.sin(rad_el), math.cos(rad_el)

        def proj_dir(x: float, y: float, z: float) -> QPointF:
            xr = x * cos_az - y * sin_az
            yr = x * sin_az + y * cos_az
            sx = -xr
            sy = -yr * sin_el - z * cos_el
            return QPointF(origin_s.x() + sx * axis_len, origin_s.y() + sy * axis_len)

        x_s = proj_dir(1, 0, 0)
        y_s = proj_dir(0, 1, 0)
        z_s = proj_dir(0, 0, 1)

        font = QFont("Segoe UI", 9, QFont.Weight.Bold)
        painter.setFont(font)

        # X Axis (Red / Length)
        painter.setPen(QPen(QColor("#ef4444"), 2.0))
        painter.drawLine(origin_s, x_s)
        painter.drawText(x_s + QPointF(4, 4), "X (L)")

        # Y Axis (Green / Width)
        painter.setPen(QPen(QColor("#22c55e"), 2.0))
        painter.drawLine(origin_s, y_s)
        painter.drawText(y_s + QPointF(4, 4), "Y (W)")

        # Z Axis (Blue / Height)
        painter.setPen(QPen(QColor("#3b82f6"), 2.0))
        painter.drawLine(origin_s, z_s)
        painter.drawText(z_s + QPointF(4, -4), "Z (H)")

    def _draw_hud(self, painter: QPainter) -> None:
        """Draws HUD viewport status overlay in top-left."""
        painter.setFont(QFont("Segoe UI", 9))
        painter.setPen(QColor("#5b6475") if self.fondo_claro else QColor("#8b97b0"))
        proj_name = "Perspectiva" if self.is_perspective else "Paralela (orto)"
        info = f"{proj_name} | Azimut {self.azimuth_deg:.0f}° | Elevación {self.elevation_deg:.0f}° | Zoom {self.zoom_factor:.2f}x"
        painter.drawText(12, 20, info)

        if self.highlighted_labels or self.highlighted_wall_indices:
            sel_text = ", ".join(sorted(lbl for lbl in self.highlighted_labels)) if self.highlighted_labels else f"Divisor #{list(self.highlighted_wall_indices)[0] + 1}"
            painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            painter.setPen(QColor(COLORS.get("highlight_edge", "#fde047")))
            painter.drawText(12, 38, f"★ Resaltado: {sel_text}")
