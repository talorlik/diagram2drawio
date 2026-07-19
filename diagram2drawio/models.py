"""
Canonical intermediate representation (IR) used by every stage of the pipeline.

Every input adapter (Mermaid parser, PlantUML parser, AI image extractor) must
produce a Graph. Every output stage (layout engine, drawio writer) consumes a
Graph. This keeps the pipeline stages fully decoupled and swappable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Node:
    id: str
    label: str
    # Raw shape hint from the source format (e.g. mermaid's [], (), {{}}, ((]))
    shape_hint: Optional[str] = None
    # "aws" | "azure" | "generic" | "actor" -- resolved by the icon library
    provider: Optional[str] = None
    # Resolved icon key from the icon library (e.g. "lambda", "s3", "vm")
    icon_key: Optional[str] = None
    # Architecture layer, e.g. "edge", "network", "compute", "data",
    # "messaging", "security", "monitoring", "other". Either taken from an
    # explicit source grouping (mermaid subgraph / plantuml package) or
    # inferred from the icon library.
    layer: Optional[str] = None
    # Explicit group/subgraph name from the source diagram, if any. Distinct
    # from `layer` because a diagram can have subgraphs that are *not*
    # architecture tiers (e.g. "AZ-1", "AZ-2" availability zones).
    group: Optional[str] = None
    # Resolved draw.io mxCell `style=` string (icon shape), set by the icon
    # resolution pass before layout/export.
    style: Optional[str] = None
    # Populated by the layout engine. x/y are relative to the parent
    # container cell (mxGraph child-geometry convention).
    x: float = 0.0
    y: float = 0.0
    width: float = 120.0
    height: float = 78.0


@dataclass
class Edge:
    id: str
    source: str
    target: str
    label: Optional[str] = None
    # "solid" | "dashed" | "dotted"
    style: str = "solid"
    # True for bidirectional arrows (mermaid <-->, plantuml <-->)
    bidirectional: bool = False


@dataclass
class Group:
    """An explicit grouping from the source diagram (mermaid subgraph /
    plantuml package/rectangle) OR a synthesized architecture-layer band
    produced by the layout engine."""
    id: str
    label: str
    node_ids: list[str] = field(default_factory=list)
    kind: str = "layer"  # "layer" | "boundary" (e.g. VPC/VNet/AZ containers)
    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 0.0


@dataclass
class Graph:
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)
    groups: dict[str, Group] = field(default_factory=dict)
    title: str = "Architecture Diagram"
    source_format: str = "unknown"
    default_provider: str = "auto"  # "aws" | "azure" | "auto"

    def add_node(self, node: Node) -> None:
        self.nodes[node.id] = node

    def add_edge(self, edge: Edge) -> None:
        self.edges.append(edge)

    def get_or_create_group(self, group_id: str, label: str, kind: str = "layer") -> Group:
        if group_id not in self.groups:
            self.groups[group_id] = Group(id=group_id, label=label, kind=kind)
        return self.groups[group_id]
