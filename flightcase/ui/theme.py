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
