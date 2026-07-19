"""
Icon resolution library.

Maps a free-text node label (e.g. "Lambda", "S3 bucket", "Azure SQL DB") to:
  - a provider ("aws" | "azure" | "generic")
  - an architecture layer ("edge" | "network" | "compute" | "data" |
    "messaging" | "security" | "monitoring" | "analytics" | "ml" | "other")
  - a ready-to-use draw.io mxCell `style` string using the official
    mxgraph.aws4 / mxgraph.azure stencil shapes that ship with draw.io, so
    nodes render as recognizable AWS/Azure service icons rather than plain
    boxes.

The underlying data lives in aws_icons.json / azure_icons.json so the
mapping can be extended or corrected without touching code (e.g. if a
resIcon name doesn't exist in the draw.io version you're using -- shape
library naming has shifted across draw.io releases).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

_ICON_DIR = Path(__file__).parent

# Generic (provider-agnostic) shapes used for actors, clients, generic
# databases/queues when no specific AWS/Azure service is recognized.
GENERIC_SHAPES = {
    "actor": "shape=umlActor;verticalLabelPosition=bottom;verticalAlign=top;html=1;outlineConnect=0;fillColor=#647687;strokeColor=#314354;fontColor=#232F3E;",
    "database": "shape=cylinder3;whiteSpace=wrap;html=1;boundedLbl=1;backgroundOutline=1;size=15;fillColor=#dae8fc;strokeColor=#6c8ebf;",
    "queue": "shape=mxgraph.basic.rect;fillColor=#fff2cc;strokeColor=#d6b656;whiteSpace=wrap;html=1;",
    "cloud": "ellipse;shape=cloud;whiteSpace=wrap;html=1;fillColor=#f5f5f5;strokeColor=#666666;",
    "generic": "rounded=1;whiteSpace=wrap;html=1;fillColor=#f5f5f5;strokeColor=#666666;",
}

# Keyword hints used to route a label to a GENERIC_SHAPES fallback and a
# best-guess layer when no AWS/Azure service keyword matched at all.
_GENERIC_HINTS = [
    (re.compile(r"\b(user|client|browser|customer|mobile app|end user|actor)\b", re.I), "edge", "actor"),
    (re.compile(r"\b(db|database|sql|postgres|mysql|mongo)\b", re.I), "data", "database"),
    (re.compile(r"\b(queue|topic|broker|kafka|mq)\b", re.I), "messaging", "queue"),
    (re.compile(r"\b(internet|external|3rd party|third[- ]party)\b", re.I), "edge", "cloud"),
]

_LAYER_ORDER = [
    "edge", "network", "security", "compute", "messaging",
    "data", "analytics", "ml", "monitoring", "other",
]


@dataclass
class IconMatch:
    provider: str          # "aws" | "azure" | "generic"
    icon_key: str
    layer: str
    style: str


class IconLibrary:
    def __init__(self):
        self._catalogs = {}
        for provider in ("aws", "azure"):
            with open(_ICON_DIR / f"{provider}_icons.json", "r", encoding="utf-8") as f:
                self._catalogs[provider] = json.load(f)

    @staticmethod
    def layer_rank(layer: str) -> int:
        return _LAYER_ORDER.index(layer) if layer in _LAYER_ORDER else len(_LAYER_ORDER)

    def _build_style(self, provider: str, entry: dict) -> str:
        colors = self._catalogs[provider]["category_colors"]
        fill = colors.get(entry["category"], colors["generic"])
        if provider == "aws":
            # AWS4 has two icon patterns that must not be mixed:
            #  - "service" (default): framed resourceIcon, requires strokeColor=#ffffff
            #  - "resource": standalone dedicated shape, requires strokeColor=none
            if entry.get("icon_pattern") == "resource":
                return (
                    "sketch=0;outlineConnect=0;fontColor=#232F3E;gradientColor=none;"
                    f"fillColor={fill};strokeColor=none;dashed=0;"
                    "verticalLabelPosition=bottom;verticalAlign=top;align=center;"
                    "html=1;fontSize=11;fontStyle=0;aspect=fixed;pointerEvents=1;"
                    f"shape={entry['res_icon']};"
                )
            return (
                "sketch=0;outlineConnect=0;fontColor=#232F3E;gradientColor=none;"
                f"fillColor={fill};strokeColor=#ffffff;dashed=0;"
                "verticalLabelPosition=bottom;verticalAlign=top;align=center;"
                "html=1;fontSize=11;fontStyle=0;aspect=fixed;"
                f"shape=mxgraph.aws4.resourceIcon;resIcon={entry['res_icon']};"
            )
        else:  # azure
            return (
                "sketch=0;outlineConnect=0;fontColor=#232F3E;"
                f"fillColor={fill};strokeColor=none;dashed=0;"
                "verticalLabelPosition=bottom;verticalAlign=top;align=center;"
                "html=1;fontSize=11;fontStyle=0;aspect=fixed;pointerEvents=1;"
                f"shape={entry['res_icon']};"
            )

    def resolve(self, label: str, provider_hint: Optional[str] = None) -> IconMatch:
        """Resolve a free-text label to the best matching icon.

        provider_hint: "aws", "azure", or "auto"/None to search both and let
        keyword specificity decide.
        """
        norm = label.lower().strip()
        candidates = ["aws", "azure"] if provider_hint in (None, "auto") else [provider_hint]

        best = None  # (specificity, provider, entry)
        for provider in candidates:
            for entry in self._catalogs[provider]["services"]:
                for kw in entry["keywords"]:
                    if kw in norm:
                        specificity = len(kw)
                        if best is None or specificity > best[0]:
                            best = (specificity, provider, entry)

        if best is not None:
            _, provider, entry = best
            return IconMatch(
                provider=provider,
                icon_key=entry["key"],
                layer=entry["layer"],
                style=self._build_style(provider, entry),
            )

        # Fallback: generic shape based on keyword hints, else plain box.
        for pattern, layer, shape_key in _GENERIC_HINTS:
            if pattern.search(norm):
                return IconMatch(provider="generic", icon_key=shape_key, layer=layer, style=GENERIC_SHAPES[shape_key])

        return IconMatch(provider="generic", icon_key="generic", layer="other", style=GENERIC_SHAPES["generic"])


_library_singleton: Optional[IconLibrary] = None


def get_icon_library() -> IconLibrary:
    global _library_singleton
    if _library_singleton is None:
        _library_singleton = IconLibrary()
    return _library_singleton
