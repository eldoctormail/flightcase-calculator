"""UI styling, color palettes, and themes for LBD Flightcase Maker."""

from pathlib import Path

# Load central stylesheet from resources
_QSS_PATH = Path(__file__).resolve().parent.parent / "resources" / "dark-desktop.qss"
if _QSS_PATH.is_file():
    DARK_THEME_QSS = _QSS_PATH.read_text(encoding="utf-8")
else:
    DARK_THEME_QSS = ""

COLORS = {
    "bg_schema": "#18181f",
    "base_edge": "#3b82f6",       # Blue
    "base_fill": "#1e293b",       # Deep slate blue
    "lid_edge": "#06b6d4",        # Cyan
    "lid_fill": "#162e3b",        # Deep slate cyan
    "profile_edge": "#f59e0b",    # Amber/Gold
    "profile_fill": "#784d12",    # Warm bronze aluminum
    "wall_edge": "#ec4899",       # Pink/Magenta
    "wall_fill": "#3b1734",       # Deep magenta
    "profile_h_edge": "#f59e0b",  # Aro hembra (tapas)
    "profile_h_fill": "#5c3b0e",
    "rueda_edge": "#94a3b8",
    "rueda_fill": "#111827",
    "rueda_freno_edge": "#f87171",
    "rueda_freno_fill": "#7f1d1d",
    "aluminio_edge": "#e2e8f0",   # Ángulos de arista del taller
    "aluminio_fill": "#94a3b8",
    "cierre_edge": "#f1f5f9",     # Cierres y bisagras
    "cierre_fill": "#cbd5e1",
    "rueda_placa_edge": "#94a3b8",
    "rueda_placa_fill": "#374151",
    "rueda_horq_edge": "#cbd5e1",
    "rueda_horq_fill": "#6b7280",
    "freno_edge": "#fca5a5",
    "freno_fill": "#dc2626",
    "base_ruedas_edge": "#a16207",
    "base_ruedas_fill": "#5a3d22",
    "remache_edge": "#e5e7eb",
    "remache_fill": "#9ca3af",
    "plato_edge": "#94a3b8",
    "plato_fill": "#3a3a3a",
    "herraje_edge": "#cbd5e1",    # Herrajes del taller (esquineros, cierres, manijas)
    "herraje_fill": "#475569",
    "equipo_edge": "#a3a3a3",     # Equipos dentro del case
    "equipo_fill": "#2b3a4a",
    "rack_frente_edge": "#d4d4d4",  # Frente de los equipos de rack
    "rack_frente_fill": "#404040",
    "espuma_edge": "#4b5563",     # Espuma con calados
    "espuma_fill": "#1f2937",
    "forro_alfombra_edge": "#52525b",   # Forro interior de alfombra
    "forro_alfombra_fill": "#27272a",
    "forro_espuma_edge": "#6b7280",     # Forro interior de espuma
    "forro_espuma_fill": "#374151",
    "cajon_edge": "#d6a35c",      # Cajones y suplementos de madera
    "cajon_fill": "#6b4a26",
    "resalte_edge": "#fde047",    # Lo que se agrega en un paso del instructivo
    "resalte_fill": "#d97706",
    "endgrain_edge": "#60a5fa",   # Blue/slate edge highlight
    "endgrain_fill": "#334155",   # Wood panel thickness cross-section
    "highlight_edge": "#fde047",  # Bright glowing electric yellow/gold
    "highlight_fill": "#d97706",  # Rich glowing amber
    "highlight_endgrain_edge": "#fef08a",  # Brilliant yellow highlight
    "highlight_endgrain_fill": "#f59e0b",  # Radiant amber endgrain
    "inner_edge": "#64748b",      # Muted slate
    "dim_line": "#e2e8f0",        # Crisp white/silver
    "dim_text": "#fbbf24",        # Warm yellow
    "cut_line": "#f59e0b",        # Dashed cut line marking
    "grid_line": "#262633",
}

# Fondo de la vista 3D: (arriba, abajo) del degradado, y la grilla del piso
FONDO_3D = {
    "oscuro": ("#1b2740", "#0b111e"),
    "claro": ("#f5f7fb", "#d6dce6"),
    "grilla": "#2a3a58",
    "grilla_clara": "#b7c0ce",
}

# Colores «realistas» de la vista 3D (relleno, arista): placa negra, aluminio y cromados.
# El color de la placa del proyecto (color_placa / color_tapa) reemplaza al de base/lid/wall.
REALISTA = {
    "base": ("#232427", "#050506"),
    "lid": ("#232427", "#050506"),
    "wall": ("#2e2f33", "#0a0a0b"),
    "canto": ("#3a3b40", "#050506"),
    "profile": ("#b9bfc8", "#5d636c"),
    "profile_h": ("#a9afb8", "#555b63"),
    "aluminio": ("#c9ced6", "#69707a"),
    "herraje": ("#c2c7cf", "#5f656e"),
    "cierre": ("#d8dce2", "#6b717a"),
    "remache": ("#d0d4da", "#7a8089"),
    "plato": ("#9ea4ad", "#4d525a"),
    "rueda": ("#1f2a44", "#0b0f18"),
    "rueda_freno": ("#1f2a44", "#0b0f18"),
    "rueda_placa": ("#b5bac2", "#5a5f67"),
    "rueda_horq": ("#c3c8cf", "#5a5f67"),
    "freno": ("#d23b3b", "#5e1414"),
    "base_ruedas": ("#2b2c30", "#0a0a0b"),
    "equipo": ("#3b4656", "#151a22"),
    "rack_frente": ("#1d1f24", "#5d636c"),
    "espuma": ("#2a2b2e", "#111214"),
    "cajon": ("#2c2d31", "#0a0a0b"),
    "resalte": ("#f59e0b", "#7c4a03"),
}
# grupos de metal: más contraste entre la cara iluminada y la de sombra
REALISTA_METAL = {"profile", "profile_h", "aluminio", "herraje", "cierre", "remache", "plato",
                  "rueda_placa", "rueda_horq"}
