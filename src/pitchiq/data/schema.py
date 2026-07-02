"""Modelos pydantic de las entidades del dominio."""

from typing import Any

from pydantic import BaseModel, Field


class Match(BaseModel):
    """Un partido del dataset (fila de load_matches)."""

    match_id: int
    match_date: str
    home_team: str
    away_team: str
    home_score: int
    away_score: int

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Match":
        """Construye un Match desde una fila (dict) del DataFrame de partidos."""
        return cls(
            match_id=row["match_id"],
            match_date=str(row["match_date"])[:10],
            home_team=row["home_team"],
            away_team=row["away_team"],
            home_score=row["home_score"],
            away_score=row["away_score"],
        )


class ZoneGrid(BaseModel):
    """Conteos de acciones defensivas de un equipo agregados en una rejilla de zonas.

    ``counts[iy][ix]``: fila ``iy`` recorre el ancho de la pista (y: 0 → 80) y
    columna ``ix`` recorre el largo (x: 0 → 120), en coordenadas StatsBomb del
    equipo analizado (ataca de izquierda a derecha).
    """

    team: str
    n_x: int = Field(gt=0, description="número de zonas a lo largo de la pista")
    n_y: int = Field(gt=0, description="número de zonas a lo ancho de la pista")
    counts: list[list[int]]

    @property
    def total(self) -> int:
        """Total de acciones defensivas agregadas en la rejilla."""
        return int(sum(sum(row) for row in self.counts))
