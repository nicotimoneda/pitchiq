"""Métricas espaciales de forma defensiva sobre freeze-frames 360.

Todas las funciones son puras y se computan SOLO sobre los jugadores visibles
del freeze-frame (ver caveat en metrics/frames.py): cuando no hay suficientes
jugadores visibles para definir la métrica, el valor por evento es NaN — nunca
se inventa. Coordenadas en la perspectiva del equipo analizado (ataca →, su
portería en x=0).
"""

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict
from scipy.spatial import ConvexHull, QhullError

from pitchiq.metrics.frames import merge_frames_events, visible_teammates
from pitchiq.metrics.pressing import defensive_actions


class SpatialResult(BaseModel):
    """Resultado de una métrica espacial: valores por evento + agregados."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    team: str
    metric: str
    per_event: pd.DataFrame

    @property
    def n_events(self) -> int:
        """Eventos con freeze-frame 360 evaluados."""
        return len(self.per_event)

    def mean(self, column: str) -> float:
        """Media del valor por evento ignorando NaN; NaN si no hay valores."""
        if self.per_event.empty or self.per_event[column].isna().all():
            return float("nan")
        return float(self.per_event[column].mean())


def _team_frames_per_event(
    frames: pd.DataFrame, events: pd.DataFrame, team: str, event_ids: pd.Series
) -> "list[tuple[str, pd.DataFrame]]":
    """Agrupa los freeze-frames mergeados por evento, solo para los ids dados."""
    merged = merge_frames_events(frames, events)
    if merged.empty:
        return []
    merged = merged[merged["event_uuid"].isin(set(event_ids))]
    return list(merged.groupby("event_uuid", sort=False))


def defensive_compactness(
    frames: pd.DataFrame, events: pd.DataFrame, team: str
) -> SpatialResult:
    """Compacidad del bloque en acciones defensivas: área de convex hull y anchura×profundidad.

    Menos área = bloque más compacto. Con < 3 compañeros visibles el hull no
    está definido y el evento vale NaN.
    """
    rows = []
    actions = defensive_actions(events, team)
    for uuid, frame in _team_frames_per_event(frames, events, team, actions["id"]):
        xy = visible_teammates(frame, team, include_keeper=False)
        hull_area = width = depth = float("nan")
        if len(xy) >= 3:
            try:
                hull_area = float(ConvexHull(xy).volume)  # .volume = área en 2D
            except QhullError:  # puntos colineales
                hull_area = float("nan")
            width = float(np.ptp(xy[:, 1]))
            depth = float(np.ptp(xy[:, 0]))
        rows.append(
            {
                "event_uuid": uuid,
                "n_visible": len(xy),
                "hull_area": hull_area,
                "width": width,
                "depth": depth,
            }
        )
    per_event = pd.DataFrame(
        rows, columns=["event_uuid", "n_visible", "hull_area", "width", "depth"]
    )
    return SpatialResult(team=team, metric="defensive_compactness", per_event=per_event)


def defensive_line_height(
    frames: pd.DataFrame, events: pd.DataFrame, team: str, n_defenders: int = 4
) -> SpatialResult:
    """Altura de la línea defensiva: media de x de los N compañeros visibles más
    retrasados (portero excluido) durante las acciones defensivas del equipo.

    Si hay menos de ``n_defenders`` compañeros visibles el evento vale NaN
    (no se estima una línea con menos jugadores de los que la definen).
    """
    rows = []
    actions = defensive_actions(events, team)
    for uuid, frame in _team_frames_per_event(frames, events, team, actions["id"]):
        xy = visible_teammates(frame, team, include_keeper=False)
        if len(xy) >= n_defenders:
            line_height = float(np.sort(xy[:, 0])[:n_defenders].mean())
        else:
            line_height = float("nan")
        rows.append(
            {"event_uuid": uuid, "n_visible": len(xy), "line_height": line_height}
        )
    per_event = pd.DataFrame(rows, columns=["event_uuid", "n_visible", "line_height"])
    return SpatialResult(team=team, metric="defensive_line_height", per_event=per_event)


def pressing_support(
    frames: pd.DataFrame, events: pd.DataFrame, team: str, radius: float = 10.0
) -> SpatialResult:
    """Soporte de presión: compañeros visibles a <= radius de la posición del
    evento Pressure (proxy de la posición del balón), sin contar al presionador.

    El conteo es un mínimo (solo visibles): la distribución real puede ser mayor.
    """
    rows = []
    pressures = events[
        (events["type"] == "Pressure")
        & (events["team"] == team)
        & events["location"].notna()
    ]
    ball_by_id = dict(zip(pressures["id"], pressures["location"]))
    for uuid, frame in _team_frames_per_event(frames, events, team, pressures["id"]):
        xy = visible_teammates(frame, team, include_keeper=False)
        ball = np.asarray(ball_by_id[uuid], dtype=float)[:2]
        if len(xy) == 0:
            support = 0
        else:
            support = int((np.linalg.norm(xy - ball, axis=1) <= radius).sum())
        rows.append({"event_uuid": uuid, "n_visible": len(xy), "support": support})
    per_event = pd.DataFrame(rows, columns=["event_uuid", "n_visible", "support"])
    return SpatialResult(team=team, metric="pressing_support", per_event=per_event)


def support_distribution(result: SpatialResult) -> "dict[int, int]":
    """Distribución del soporte de presión: {n compañeros dentro del radio: eventos}."""
    if result.per_event.empty:
        return {}
    counts = result.per_event["support"].value_counts().sort_index()
    return {int(k): int(v) for k, v in counts.items()}
