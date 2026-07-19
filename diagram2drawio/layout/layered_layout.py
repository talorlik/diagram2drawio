"""
Layered (Sugiyama-style) auto-layout engine.

Produces the "clean, readable layering" enterprise architecture look: one
horizontal band per architecture tier (Edge -> Network -> Security ->
Compute -> Messaging -> Data -> Analytics/ML -> Monitoring), each rendered
as a labelled, dashed-outline container with its nodes arranged in a tidy
grid. If the source diagram already defines explicit groups (Mermaid
subgraph, PlantUML package, or AI-image-extracted boundary boxes such as a
VPC/VNet/availability zone), those are used as the containers instead --
ordered top-to-bottom by the average architecture-layer rank of the nodes
they contain, so a hand-drawn diagram's own grouping still comes out in a
sensible top-down flow.

All positions in the returned Graph are ready to hand to the drawio writer:
  - Container (Group) x/y are absolute canvas coordinates.
  - Node x/y are relative to their parent container (mxGraph child geometry
    convention) and default to (0, 0) relative + absolute canvas position
    when a node has no container.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from ..icons.icon_library import get_icon_library
from ..models import Graph, Group

NODE_W = 120
NODE_H = 78
GAP_X = 40
GAP_Y = 36
MAX_PER_ROW = 6
CONTAINER_H_PADDING = 30
CONTAINER_TOP_PADDING = 40  # room for the container title label
CONTAINER_BOTTOM_PADDING = 20
CONTAINER_GAP_Y = 50
CANVAS_MARGIN = 40
TITLE_BAND_HEIGHT = 60


@dataclass
class LayoutResult:
    canvas_width: float
    canvas_height: float
    title_height: float
    container_order: list[str]


def _canonical_layer_containers(graph: Graph) -> list[Group]:
    library = get_icon_library()
    by_layer: dict[str, list[str]] = {}
    for node in graph.nodes.values():
        layer = node.layer or "other"
        by_layer.setdefault(layer, []).append(node.id)

    ordered_layers = sorted(by_layer.keys(), key=library.layer_rank)
    labels = {
        "edge": "Edge / Client Layer", "network": "Network Layer",
        "security": "Security Layer", "compute": "Compute Layer",
        "messaging": "Messaging & Integration Layer", "data": "Data Layer",
        "analytics": "Analytics Layer", "ml": "ML / AI Layer",
        "monitoring": "Monitoring & Observability Layer", "other": "Other Components",
    }
    groups = []
    for layer in ordered_layers:
        g = Group(id=f"layer_{layer}", label=labels.get(layer, layer.title()), node_ids=by_layer[layer], kind="layer")
        groups.append(g)
    return groups


def _order_explicit_groups(graph: Graph) -> list[Group]:
    library = get_icon_library()
    groups = [g for g in graph.groups.values() if g.node_ids]

    def avg_rank(g: Group) -> float:
        ranks = [library.layer_rank(graph.nodes[nid].layer or "other") for nid in g.node_ids if nid in graph.nodes]
        return sum(ranks) / len(ranks) if ranks else library.layer_rank("other")

    groups.sort(key=avg_rank)

    grouped_ids = {nid for g in groups for nid in g.node_ids}
    orphans = [nid for nid in graph.nodes if nid not in grouped_ids]
    if orphans:
        orphan_layers: dict[str, list[str]] = {}
        for nid in orphans:
            orphan_layers.setdefault(graph.nodes[nid].layer or "other", []).append(nid)
        for layer in sorted(orphan_layers.keys(), key=library.layer_rank):
            # Prefer folding orphans into an existing explicit group whose
            # title already matches this layer (e.g. a PlantUML `package
            # "Edge" { ... }` block) instead of creating a second,
            # confusingly-identically-labelled container.
            target = next((g for g in groups if layer in g.label.lower()), None)
            if target is not None:
                target.node_ids.extend(orphan_layers[layer])
            else:
                groups.append(Group(id=f"layer_{layer}", label=layer.title(), node_ids=orphan_layers[layer], kind="layer"))
    return groups


def _order_nodes_in_container(graph: Graph, node_ids: list[str], prev_positions: dict[str, int]) -> list[str]:
    """Lightweight barycenter ordering: nodes whose predecessors (from the
    previous container) sit further left are pulled left too, which keeps
    vertical chains visually aligned and reduces edge crossings."""
    if not prev_positions:
        return node_ids

    incoming: dict[str, list[str]] = {nid: [] for nid in node_ids}
    for edge in graph.edges:
        if edge.target in incoming and edge.source in prev_positions:
            incoming[edge.target].append(edge.source)
        if edge.bidirectional and edge.source in incoming and edge.target in prev_positions:
            incoming[edge.source].append(edge.target)

    def key(nid: str):
        preds = incoming.get(nid, [])
        if not preds:
            return (1, 0)
        avg = sum(prev_positions[p] for p in preds) / len(preds)
        return (0, avg)

    return sorted(node_ids, key=key)


def apply_layered_layout(graph: Graph) -> LayoutResult:
    has_explicit_groups = any(g.node_ids for g in graph.groups.values())
    containers = _order_explicit_groups(graph) if has_explicit_groups else _canonical_layer_containers(graph)

    row_capacities = [min(len(c.node_ids), MAX_PER_ROW) or 1 for c in containers]
    max_row_width_nodes = max(row_capacities) if row_capacities else 1
    canvas_content_width = max_row_width_nodes * NODE_W + (max_row_width_nodes - 1) * GAP_X + 2 * CONTAINER_H_PADDING

    y_cursor = TITLE_BAND_HEIGHT
    prev_positions: dict[str, int] = {}
    container_order: list[str] = []

    graph.groups = {}  # rebuilt below in final render order

    for container in containers:
        ordered_ids = _order_nodes_in_container(graph, container.node_ids, prev_positions)
        n = len(ordered_ids)
        cols = min(n, MAX_PER_ROW) or 1
        rows = math.ceil(n / cols) if n else 1

        row_width = cols * NODE_W + (cols - 1) * GAP_X
        row_start_x = CONTAINER_H_PADDING + max(0, (canvas_content_width - 2 * CONTAINER_H_PADDING - row_width) / 2)

        new_positions: dict[str, int] = {}
        for idx, nid in enumerate(ordered_ids):
            row, col = divmod(idx, cols)
            items_in_this_row = min(cols, n - row * cols)
            this_row_width = items_in_this_row * NODE_W + (items_in_this_row - 1) * GAP_X
            this_row_start_x = CONTAINER_H_PADDING + max(0, (canvas_content_width - 2 * CONTAINER_H_PADDING - this_row_width) / 2)
            node = graph.nodes[nid]
            node.x = this_row_start_x + col * (NODE_W + GAP_X)
            node.y = CONTAINER_TOP_PADDING + row * (NODE_H + GAP_Y)
            node.width, node.height = NODE_W, NODE_H
            new_positions[nid] = col  # column used as the "horizontal slot" for barycenter ordering downstream

        container_height = CONTAINER_TOP_PADDING + rows * NODE_H + (rows - 1) * GAP_Y + CONTAINER_BOTTOM_PADDING
        container.x = CANVAS_MARGIN
        container.y = y_cursor
        container.width = canvas_content_width
        container.height = container_height

        graph.groups[container.id] = container
        container_order.append(container.id)

        y_cursor += container_height + CONTAINER_GAP_Y
        prev_positions = new_positions

    canvas_width = canvas_content_width + 2 * CANVAS_MARGIN
    canvas_height = y_cursor - CONTAINER_GAP_Y + CANVAS_MARGIN

    return LayoutResult(
        canvas_width=canvas_width,
        canvas_height=canvas_height,
        title_height=TITLE_BAND_HEIGHT,
        container_order=container_order,
    )
