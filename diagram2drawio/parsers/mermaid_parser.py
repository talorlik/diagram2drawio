"""
Mermaid flowchart/graph parser.

Supports the subset of Mermaid syntax commonly used for architecture
diagrams:

  flowchart TD / graph LR ...
  subgraph "Layer Title"
    A[Label]
    ...
  end
  A[Label] --> B(Label)
  A -->|label| B
  A -- label --> B
  A -.->|label| B
  A ==> B
  A <--> B
  class A,B aws        (optional provider hint override)

It intentionally does not implement the full Mermaid grammar (no styling
directives, click handlers, etc.) -- those are irrelevant for architecture
extraction and are silently ignored.
"""
from __future__ import annotations

import re

from ..models import Edge, Graph, Node

_SHAPE_PATTERNS = [
    (re.compile(r"^\[\((.*)\)\]$", re.S), "cylinder"),
    (re.compile(r"^\(\((.*)\)\)$", re.S), "circle"),
    (re.compile(r"^\{\{(.*)\}\}$", re.S), "hexagon"),
    (re.compile(r"^\{(.*)\}$", re.S), "rhombus"),
    (re.compile(r"^\[/(.*)/\]$", re.S), "parallelogram"),
    (re.compile(r"^\[\\(.*)\\\]$", re.S), "parallelogram"),
    (re.compile(r"^>(.*)\]$", re.S), "flag"),
    (re.compile(r"^\((.*)\)$", re.S), "rounded"),
    (re.compile(r"^\[(.*)\]$", re.S), "rect"),
]

_NODE_ID_RE = re.compile(r'^([A-Za-z0-9_\-]+)(.*)$', re.S)

_ARROW_DEFS = [
    ("bidirectional_dashed", r"<-{1,2}\.{1,2}->", "dashed", True),
    ("bidirectional_solid", r"<-{1,3}>", "solid", True),
    ("dashed", r"-{1,2}\.{1,2}->", "dashed", False),
    ("thick", r"={1,3}>", "solid", False),
    ("solid_arrow", r"-{1,3}>", "solid", False),
    ("plain_line", r"-{2,3}(?!>)", "solid", False),
]
_ARROW_RE = re.compile("|".join(f"(?P<{name}>{pat})" for name, pat, _, _ in _ARROW_DEFS))
_ARROW_STYLE_BY_GROUP = {name: (style, bidi) for name, _, style, bidi in _ARROW_DEFS}

_SUBGRAPH_START_RE = re.compile(r'^subgraph\s+(.*)$', re.I)
_SUBGRAPH_END_RE = re.compile(r'^end$', re.I)
_CLASS_RE = re.compile(r'^class\s+([A-Za-z0-9_,\-\s]+)\s+([A-Za-z]+)\s*$', re.I)
_DIRECTIVE_RE = re.compile(r'^(flowchart|graph)\s+', re.I)


def _slugify(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', '_', text.lower()).strip('_') or "group"


def _strip_quotes(text: str) -> str:
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ('"', "'"):
        return text[1:-1].strip()
    return text


def _parse_node_token(token: str):
    token = token.strip()
    m = _NODE_ID_RE.match(token)
    if not m:
        return token, token, None
    node_id, rest = m.group(1), m.group(2).strip()
    if not rest:
        return node_id, node_id, None
    for pattern, shape in _SHAPE_PATTERNS:
        mm = pattern.match(rest)
        if mm:
            return node_id, _strip_quotes(mm.group(1)), shape
    return node_id, rest, None


def _normalize_embedded_labels(line: str) -> str:
    line = re.sub(r'--\s+([^\-|>]+?)\s+-->', r'-->|\1|', line)
    line = re.sub(r'-\.\s+([^.\|>]+?)\s+\.->', r'-.->|\1|', line)
    line = re.sub(r'==\s+([^=\|>]+?)\s+==>', r'==>|\1|', line)
    return line


def parse_mermaid(text: str) -> Graph:
    graph = Graph(source_format="mermaid")
    group_stack: list[str] = []
    edge_counter = 0

    def register_node(token: str) -> str:
        node_id, label, shape = _parse_node_token(token)
        if node_id not in graph.nodes:
            graph.add_node(Node(id=node_id, label=label, shape_hint=shape))
        else:
            # Upgrade label if this occurrence carries an explicit shape/label
            # and the existing node currently only has the bare id as label.
            existing = graph.nodes[node_id]
            if shape and existing.label == existing.id:
                existing.label = label
                existing.shape_hint = shape
        if group_stack:
            top_group_id = group_stack[-1]
            graph.nodes[node_id].group = top_group_id
            graph.groups[top_group_id].node_ids.append(node_id)
        return node_id

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("%%"):
            continue
        if _DIRECTIVE_RE.match(line):
            continue

        sg = _SUBGRAPH_START_RE.match(line)
        if sg:
            title_raw = sg.group(1).strip()
            # subgraph ID ["Title"]  OR subgraph "Title" OR subgraph ID
            m = re.match(r'^([A-Za-z0-9_\-]+)\s*\[(.*)\]$', title_raw)
            if m:
                group_id, title = m.group(1), _strip_quotes(m.group(2))
            else:
                title = _strip_quotes(title_raw)
                group_id = _slugify(title)
            graph.get_or_create_group(group_id, title, kind="layer")
            group_stack.append(group_id)
            continue

        if _SUBGRAPH_END_RE.match(line):
            if group_stack:
                group_stack.pop()
            continue

        cls = _CLASS_RE.match(line)
        if cls:
            ids = [i.strip() for i in cls.group(1).split(",") if i.strip()]
            provider = cls.group(2).lower()
            if provider in ("aws", "azure"):
                for nid in ids:
                    if nid in graph.nodes:
                        graph.nodes[nid].provider = provider
            continue

        line = _normalize_embedded_labels(line)

        # Extract |label| segment if present.
        label = None
        pipe_m = re.search(r'\|([^|]*)\|', line)
        if pipe_m:
            label = pipe_m.group(1).strip()
            line = line[: pipe_m.start()] + line[pipe_m.end():]

        arrow_m = _ARROW_RE.search(line)
        if not arrow_m:
            # No edge on this line -- could be a standalone node declaration,
            # possibly with a trailing shape like A[Label]
            if line:
                register_node(line)
            continue

        left_raw = line[: arrow_m.start()].strip()
        right_raw = line[arrow_m.end():].strip()
        group_name = arrow_m.lastgroup
        style, bidirectional = _ARROW_STYLE_BY_GROUP[group_name]

        left_id = register_node(left_raw)
        # Right side may itself continue with another arrow (chained edges
        # like A --> B --> C); handle iteratively.
        remainder = right_raw
        prev_id = left_id
        while True:
            next_arrow = _ARROW_RE.search(remainder)
            if next_arrow:
                seg = remainder[: next_arrow.start()].strip()
                node_id = register_node(seg)
                edge_counter += 1
                graph.add_edge(Edge(id=f"e{edge_counter}", source=prev_id, target=node_id,
                                     label=label, style=style, bidirectional=bidirectional))
                label = None
                next_group = next_arrow.lastgroup
                style, bidirectional = _ARROW_STYLE_BY_GROUP[next_group]
                prev_id = node_id
                remainder = remainder[next_arrow.end():].strip()
            else:
                node_id = register_node(remainder)
                edge_counter += 1
                graph.add_edge(Edge(id=f"e{edge_counter}", source=prev_id, target=node_id,
                                     label=label, style=style, bidirectional=bidirectional))
                break

    return graph
