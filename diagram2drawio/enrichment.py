"""
Enrichment pass: resolve every node's provider/layer/icon/style using the
icon library. Runs after parsing/extraction and before layout, so the
layout engine can group and order nodes by architecture layer.
"""
from __future__ import annotations

from .icons.icon_library import get_icon_library
from .models import Graph


def enrich_graph_with_icons(graph: Graph, provider: str = "auto") -> Graph:
    """Resolve provider/layer/icon_key/style for every node in place.

    provider: "aws" | "azure" | "auto". In "auto" mode each node's provider
    is inferred independently from its label so mixed AWS+Azure diagrams
    (e.g. a hybrid/multi-cloud architecture) still render with the correct
    icon set per node.
    """
    library = get_icon_library()
    for node in graph.nodes.values():
        hint = node.provider if node.provider in ("aws", "azure") else (
            None if provider == "auto" else provider
        )
        match = library.resolve(node.label, provider_hint=hint)
        node.provider = match.provider
        node.icon_key = match.icon_key
        node.layer = match.layer
        node.style = match.style
    return graph
