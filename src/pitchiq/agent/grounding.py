"""Validador de grounding: cada cifra del informe debe salir de una herramienta.

El "100 % grounded" no es una promesa del prompt: es este check. Se extraen
todos los números del texto y se cotejan (con tolerancia de redondeo) contra
las salidas reales de las herramientas recogidas en el estado del grafo.
"""

import math
import re

from pydantic import BaseModel

# Números con decimales por punto o coma: 52.9 / 52,9 / 68 / 10.84
_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")

# Números que no son afirmaciones métricas y se excluyen del check:
# años (2023, 2024) y temporadas (2023/24)
_YEAR_RE = re.compile(r"^(19|20)\d{2}$")
_SEASON_RE = re.compile(r"\b(19|20)\d{2}[/-]\d{2}\b")


class Figure(BaseModel):
    """Una cifra extraída del texto del informe."""

    text: str  # tal y como aparece en el informe
    value: float
    grounded: bool
    matched_metric: "str | None" = None


class GroundingReport(BaseModel):
    """Resultado del check: qué cifras están respaldadas y cuáles no."""

    figures: "list[Figure]"
    ratio: float  # respaldadas / total (1.0 si el texto no tiene cifras)

    @property
    def ungrounded(self) -> "list[Figure]":
        """Cifras sin respaldo en las salidas de herramientas."""
        return [f for f in self.figures if not f.grounded]

    @property
    def is_grounded(self) -> bool:
        """True si todas las cifras del informe están respaldadas."""
        return not self.ungrounded


def extract_figures(text: str) -> "list[tuple[str, float]]":
    """Extrae los números del texto (coma o punto decimal), excluyendo años."""
    text = _SEASON_RE.sub(" ", text)  # "2023/24" no es una cifra métrica
    figures = []
    for match in _NUMBER_RE.finditer(text):
        raw = match.group()
        if _YEAR_RE.match(raw):
            # excluir años y temporadas tipo 2023/24
            continue
        figures.append((raw, float(raw.replace(",", "."))))
    return figures


def _matches(value: float, evidence_value: float, rel_tol: float) -> bool:
    """True si ``value`` es el valor de evidencia, admitiendo su redondeo."""
    if math.isclose(value, evidence_value, rel_tol=rel_tol, abs_tol=1e-9):
        return True
    # el redactor puede redondear: 52.87 escrito como 52.9 o como 53
    decimals = 0
    if "." in f"{value}":
        decimals = len(f"{value}".split(".")[1].rstrip("0"))
    return round(evidence_value, decimals) == value


def validate_grounding(
    text: str, evidence: "dict[str, float]", rel_tol: float = 1e-4
) -> GroundingReport:
    """Coteja cada cifra del informe contra la evidencia de las herramientas."""
    figures: list[Figure] = []
    for raw, value in extract_figures(text):
        matched = next(
            (name for name, ev in evidence.items() if _matches(value, ev, rel_tol)),
            None,
        )
        figures.append(
            Figure(
                text=raw, value=value, grounded=matched is not None,
                matched_metric=matched,
            )
        )
    grounded = sum(f.grounded for f in figures)
    ratio = grounded / len(figures) if figures else 1.0
    return GroundingReport(figures=figures, ratio=ratio)
