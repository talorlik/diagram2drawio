"""
PlantUML component/deployment diagram parser.

Supports the common subset used for architecture diagrams:

  package "Web Tier" {
    [Load Balancer] as LB
    component "Web Server" as WS
  }
  database "Orders DB" as DB
  cloud "CDN" as CDN
  actor "User" as U

  U --> CDN
  CDN --> LB : HTTPS
  LB -down-> WS
  WS ..> DB : SQL (async)
  LB <--> WS

Containers (package / rectangle / node / cloud used as a block with `{`)
become layer groups, mirroring Mermaid's `subgraph`.
"""
from __future__ import annotations

import re

from ..models import Edge, Graph, Node

_ELEMENT_KEYWORDS = (
    "component", "database", "cloud", "node", "rectangle",
    "actor", "interface", "usecase", "queue", "storage", "package", "folder",
)

_SHAPE_BY_KEYWORD = {
    "database": "cylinder",
    "storage": "cylinder",
    "cloud": "cloud",
    "actor": "actor",
    "queue": "queue",
}

_ELEMENT_RE = re.compile(
    r'^(' + "|".join(_ELEMENT_KEYWORDS) + r')\s+(".*?"|\S+)(?:\s+as\s+(\S+))?\s*(\{)?\s*$',
    re.I,
)
_BRACKET_ELEMENT_RE = re.compile(r'^\[(.*?)\](?:\s+as\s+(\S+))?\s*(\{)?\s*$')
_CONTAINER_KEYWORDS = ("package", "rectangle", "node", "folder", "cloud")

_DIRECTION_RE = re.compile(r'-(up|down|left|right)-', re.I)
_ARROW_RE = re.compile(r'(<-{1,2}>|<\.{2,4}>|-{1,2}>|\.{2,4}>)')
_REL_LINE_RE = re.compile(r'^(\S+)\s*(.+?)\s*(\S+)\s*(?::\s*(.*))?$')


def _strip_quotes(text: str) -> str:
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ('"', "'"):
        return text[1:-1].strip()
    return text


def _slugify(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', '_', text.lower()).strip('_') or "group"


def parse_plantuml(text: str) -> Graph:
    graph = Graph(source_format="plantuml")
    group_stack: list[str] = []
    edge_counter = 0
    auto_id_counter = 0

    def new_auto_id() -> str:
        nonlocal auto_id_counter
        auto_id_counter += 1
        return f"n{auto_id_counter}"

    def register_element(alias: str, label: str, shape_hint) -> str:
        node_id = alias
        if node_id not in graph.nodes:
            graph.add_node(Node(id=node_id, label=label, shape_hint=shape_hint))
        if group_stack:
            top_group_id = group_stack[-1]
            graph.nodes[node_id].group = top_group_id
            graph.groups[top_group_id].node_ids.append(node_id)
        return node_id

    def ensure_node_by_token(token: str) -> str:
        """Relationship endpoints reference elements by alias (or literal
        bracket name if never declared) -- create a bare node on the fly if
        it wasn't declared with an explicit `component ... as X` line."""
        token = token.strip()
        m = re.match(r'^\[(.*)\]$', token)
        if m:
            label = m.group(1)
            node_id = _slugify(label)
            if node_id not in graph.nodes:
                graph.add_node(Node(id=node_id, label=label))
            return node_id
        if token not in graph.nodes:
            graph.add_node(Node(id=token, label=token))
        return token

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("'") or line.startswith("@") or line.startswith("!"):
            continue
        if line.lower().startswith(("title", "skinparam", "note", "hide", "left to right", "top to bottom")):
            continue

        if line == "}":
            if group_stack:
                group_stack.pop()
            continue

        em = _ELEMENT_RE.match(line)
        bm = None if em else _BRACKET_ELEMENT_RE.match(line)

        if em or bm:
            if em:
                keyword = em.group(1).lower()
                name = _strip_quotes(em.group(2))
                alias = em.group(3) or _slugify(name)
                is_container_start = bool(em.group(4))
                shape_hint = _SHAPE_BY_KEYWORD.get(keyword)
            else:
                keyword = "component"
                name = bm.group(1)
                alias = bm.group(2) or _slugify(name)
                is_container_start = bool(bm.group(3))
                shape_hint = None

            if is_container_start and keyword in _CONTAINER_KEYWORDS:
                graph.get_or_create_group(alias, name, kind="layer")
                group_stack.append(alias)
            else:
                register_element(alias, name, shape_hint)
            continue

        # Relationship line -- normalize direction hints, then locate arrow.
        norm_line = _DIRECTION_RE.sub("--", line)
        arrow_m = _ARROW_RE.search(norm_line)
        if not arrow_m:
            continue  # unrecognized directive; ignore rather than fail hard

        left_raw = norm_line[: arrow_m.start()].strip()
        right_and_label = norm_line[arrow_m.end():].strip()
        label = None
        if ":" in right_and_label:
            right_raw, label = right_and_label.split(":", 1)
            right_raw, label = right_raw.strip(), label.strip()
        else:
            right_raw = right_and_label

        arrow_token = arrow_m.group(0)
        bidirectional = arrow_token.startswith("<")
        style = "dashed" if "." in arrow_token else "solid"

        source_id = ensure_node_by_token(left_raw)
        target_id = ensure_node_by_token(right_raw)
        edge_counter += 1
        graph.add_edge(Edge(id=f"e{edge_counter}", source=source_id, target=target_id,
                             label=label, style=style, bidirectional=bidirectional))

    return graph
