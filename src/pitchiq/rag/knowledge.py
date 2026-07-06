"""Carga y validación del glosario táctico (BORRADOR pendiente de revisión humana).

El glosario aporta interpretación, nunca cifras: un validador rechaza cualquier
entrada cuyo texto contenga dígitos, porque el RAG no puede ser fuente de
números (romperia el grounding de M4). Ninguna entrada es autoritativa hasta
que un humano la marque como revisada.
"""

import re
from pathlib import Path

import yaml
from pydantic import BaseModel, field_validator

GLOSSARY_PATH = Path(__file__).resolve().parent.parent / "data" / "knowledge" / "glossary.yaml"

_DIGIT_RE = re.compile(r"\d")


class ConceptEntry(BaseModel):
    """Una entrada del glosario táctico."""

    concepto: str
    definicion: str
    interpretacion: str
    fuente: str = "pendiente de revisión humana"
    revisado: bool = False

    @field_validator("definicion", "interpretacion")
    @classmethod
    def sin_cifras(cls, v: str) -> str:
        """El glosario no puede contener cifras: el RAG no aporta números."""
        if _DIGIT_RE.search(v):
            raise ValueError(
                "el texto del glosario contiene dígitos; el RAG aporta "
                "interpretación, nunca números (las cifras salen de las tools)"
            )
        return v

    def as_context(self) -> str:
        """Representación de la entrada para inyectar en el prompt del redactor."""
        return f"{self.concepto}: {self.definicion} Interpretación: {self.interpretacion}"


def load_glossary(path: Path = GLOSSARY_PATH) -> "list[ConceptEntry]":
    """Carga el glosario YAML y lo valida entrada a entrada."""
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return [ConceptEntry.model_validate(entry) for entry in raw]


def unreviewed_count(entries: "list[ConceptEntry]") -> int:
    """Cuántas entradas siguen pendientes de revisión humana."""
    return sum(1 for e in entries if not e.revisado)


def review_status(entries: "list[ConceptEntry]") -> str:
    """Resumen legible del estado de revisión, para el humano que revisa."""
    pending = unreviewed_count(entries)
    if pending == 0:
        return f"glosario revisado: {len(entries)} entradas validadas por un humano"
    nombres = ", ".join(e.concepto for e in entries if not e.revisado)
    return (
        f"⚠️ glosario EN REVISIÓN: {pending}/{len(entries)} entradas pendientes "
        f"de revisión humana ({nombres})"
    )
