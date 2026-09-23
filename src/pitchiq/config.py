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

# Dimensiones de pista en coordenadas StatsBomb (yardas)
PITCH_LENGTH = 120.0
PITCH_WIDTH = 80.0

# StatsBomb mide en yardas; todo lo que se publica (herramientas del LLM, web)
# se convierte a metros. Las métricas internas trabajan en coordenadas StatsBomb.
YARDA_M = 0.9144
PITCH_LENGTH_M = PITCH_LENGTH * YARDA_M  # 109,7 m
PITCH_WIDTH_M = PITCH_WIDTH * YARDA_M  # 73,2 m


def a_metros(yardas: float) -> float:
    """Distancia en yardas StatsBomb → metros."""
    return yardas * YARDA_M


def a_yardas(metros: float) -> float:
    """Distancia en metros → yardas StatsBomb (para umbrales definidos en metros)."""
    return metros / YARDA_M
