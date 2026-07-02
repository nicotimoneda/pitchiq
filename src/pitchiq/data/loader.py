"""Carga de StatsBomb Open Data con cache local para no descargar en cada ejecución."""

import warnings
from pathlib import Path

import pandas as pd
from statsbombpy import sb

from pitchiq import config


def _cache_path(name: str) -> Path:
    """Ruta del fichero de cache para una clave dada, creando el directorio."""
    config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return config.CACHE_DIR / f"{name}.json"


def _read_cache(name: str) -> pd.DataFrame | None:
    """Devuelve el DataFrame cacheado bajo esa clave, o None si no existe."""
    path = _cache_path(name)
    if not path.exists():
        return None
    return pd.read_json(path, orient="records")


def _write_cache(name: str, df: pd.DataFrame) -> None:
    """Serializa un DataFrame a JSON en el directorio de cache."""
    df.to_json(_cache_path(name), orient="records")


def load_matches(
    competition_id: int = config.COMPETITION_ID,
    season_id: int = config.SEASON_ID,
) -> pd.DataFrame:
    """Devuelve los partidos de la competición/temporada (34 para Leverkusen 23/24)."""
    key = f"matches_{competition_id}_{season_id}"
    cached = _read_cache(key)
    if cached is not None:
        return cached
    matches = sb.matches(competition_id=competition_id, season_id=season_id)
    _write_cache(key, matches)
    return matches


def load_events(match_id: int) -> pd.DataFrame:
    """Devuelve los eventos de un partido (incluye a los dos equipos)."""
    key = f"events_{match_id}"
    cached = _read_cache(key)
    if cached is not None:
        return cached
    events = sb.events(match_id=match_id)
    _write_cache(key, events)
    return events


def _flatten_frames(raw: list[dict]) -> pd.DataFrame:
    """Aplana los frames 360 crudos a una fila por jugador en cada freeze-frame."""
    rows = [
        {
            "event_uuid": frame["event_uuid"],
            "match_id": int(frame["match_id"]),
            "teammate": player["teammate"],
            "actor": player["actor"],
            "keeper": player["keeper"],
            "location": player["location"],
        }
        for frame in raw
        for player in frame.get("freeze_frame") or []
    ]
    return pd.DataFrame(rows)


def load_frames(match_id: int) -> pd.DataFrame:
    """Devuelve los freeze-frames 360 del partido; DataFrame vacío si no hay 360."""
    key = f"frames_{match_id}"
    cached = _read_cache(key)
    if cached is not None:
        return cached
    try:
        # fmt="dict" evita un bug de aplanado de statsbombpy (InvalidIndexError)
        frames = _flatten_frames(sb.frames(match_id=match_id, fmt="dict"))
    except Exception as exc:  # partido sin 360: no se cachea por si es transitorio
        warnings.warn(f"sin datos 360 para el partido {match_id}: {exc}", stacklevel=2)
        return pd.DataFrame()
    _write_cache(key, frames)
    return frames
