"""Constantes del proyecto: competición, temporada y rutas locales."""

from pathlib import Path

# Bundesliga 2023/24 (Bayer Leverkusen, temporada del título)
COMPETITION_ID = 9
SEASON_ID = 281

DEFAULT_TEAM = "Bayer Leverkusen"

# Raíz del repo (dos niveles por encima de src/pitchiq)
ROOT_DIR = Path(__file__).resolve().parents[2]

# Cache local de descargas de StatsBomb (no se versiona)
CACHE_DIR = ROOT_DIR / "data" / "cache"

# Salida de figuras generadas por los scripts
FIGURES_DIR = ROOT_DIR / "figures"

# Dimensiones de pista en coordenadas StatsBomb
PITCH_LENGTH = 120.0
PITCH_WIDTH = 80.0
