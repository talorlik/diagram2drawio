"""
AI pre-processing step: turn a raster/vector diagram image (screenshot,
whiteboard photo, exported PNG/JPG of an architecture diagram, etc.) into the
same canonical Graph used by the Mermaid/PlantUML parsers.

This calls a vision-capable LLM (OpenAI GPT-4o/4o-mini or Anthropic Claude)
and asks it to return strict JSON describing components, connections, and
approximate layout/grouping. That keeps the "understand the picture" problem
where it belongs (a multimodal model) while every downstream stage --
icon resolution, layered layout, drawio XML generation -- stays deterministic
and testable.

Usage:
    from diagram2drawio.extraction.image_extractor import extract_from_image
    graph = extract_from_image("architecture.png", api_provider="openai",
                                api_key=os.environ["OPENAI_API_KEY"])

Set `mock=True` (or omit an API key) to run a small deterministic stub
extractor instead of calling out to a real model -- useful for testing the
rest of the pipeline (layout + drawio export) without API credentials, and
as a template for wiring in an on-prem/self-hosted vision model.
"""
from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
from pathlib import Path
from typing import Optional

import requests

from ..models import Edge, Graph, Node

EXTRACTION_SYSTEM_PROMPT = """You are an expert cloud solutions architect. You will be shown an image of a \
system/cloud architecture diagram (hand-drawn, whiteboard photo, or exported from a diagramming tool).

Extract every component and connection you can identify and return ONLY a single JSON object (no prose, no \
markdown fences) with this exact shape:

{
  "title": "short descriptive title for the diagram",
  "nodes": [
    {"id": "unique_snake_case_id", "label": "human readable name as shown/implied, e.g. 'API Gateway' or 'Orders DB'",
     "group": "name of the enclosing box/lane/boundary this belongs to, if any, else null"}
  ],
  "edges": [
    {"source": "node_id", "target": "node_id", "label": "label on the arrow/line if any, else null",
     "style": "solid or dashed based on the line style in the image", "bidirectional": false}
  ],
  "groups": [
    {"id": "group_id matching the group field above", "label": "the box/lane title as shown, e.g. 'VPC', 'Data Tier', 'us-east-1'"}
  ]
}

Rules:
- Prefer the official AWS/Azure/GCP service name if the icon/label makes the service identifiable
  (e.g. "Lambda", "S3", "RDS", "Azure Functions", "Cosmos DB"). If it's a generic box, keep the label as written.
- Every edge's source/target MUST reference a node id that also appears in "nodes".
- If the diagram has swimlanes, tiers, VPC/VNet boundaries, or availability-zone boxes, capture them in "groups" and
  set each contained node's "group" field accordingly -- this drives the layered layout of the regenerated diagram.
- Output strictly valid JSON. Do not wrap it in markdown code fences.
"""


def _encode_image(image_path: str) -> tuple[str, str]:
    mime, _ = mimetypes.guess_type(image_path)
    mime = mime or "image/png"
    with open(image_path, "rb") as f:
        data = base64.b64encode(f.read()).decode("ascii")
    return mime, data


def _extract_json_block(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"```$", "", text).strip()
    # Fall back to grabbing the outermost {...} if the model added prose.
    if not text.startswith("{"):
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            text = m.group(0)
    return json.loads(text)


def _call_openai(image_path: str, api_key: str, model: str) -> dict:
    mime, b64 = _encode_image(image_path)
    resp = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Extract the architecture graph from this diagram."},
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                    ],
                },
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        },
        timeout=120,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    return _extract_json_block(content)


def _call_anthropic(image_path: str, api_key: str, model: str) -> dict:
    mime, b64 = _encode_image(image_path)
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": 4096,
            "system": EXTRACTION_SYSTEM_PROMPT,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": mime, "data": b64}},
                        {"type": "text", "text": "Extract the architecture graph from this diagram."},
                    ],
                }
            ],
        },
        timeout=120,
    )
    resp.raise_for_status()
    content = resp.json()["content"][0]["text"]
    return _extract_json_block(content)


def _mock_extract(image_path: str) -> dict:
    """Deterministic stand-in used for tests/demos when no API key is
    configured. Real usage should call OpenAI/Anthropic (see above)."""
    name = Path(image_path).stem.replace("_", " ").title()
    return {
        "title": f"{name} (mock extraction -- configure an API key for real image extraction)",
        "groups": [{"id": "edge", "label": "Edge"}, {"id": "app", "label": "Application"}, {"id": "data", "label": "Data"}],
        "nodes": [
            {"id": "user", "label": "User", "group": "edge"},
            {"id": "cdn", "label": "CloudFront", "group": "edge"},
            {"id": "api", "label": "API Gateway", "group": "app"},
            {"id": "svc", "label": "Lambda", "group": "app"},
            {"id": "db", "label": "DynamoDB", "group": "data"},
        ],
        "edges": [
            {"source": "user", "target": "cdn", "label": None, "style": "solid", "bidirectional": False},
            {"source": "cdn", "target": "api", "label": "HTTPS", "style": "solid", "bidirectional": False},
            {"source": "api", "target": "svc", "label": None, "style": "solid", "bidirectional": False},
            {"source": "svc", "target": "db", "label": "query", "style": "solid", "bidirectional": False},
        ],
    }


def _payload_to_graph(payload: dict) -> Graph:
    graph = Graph(source_format="image", title=payload.get("title", "Architecture Diagram"))

    for g in payload.get("groups", []) or []:
        graph.get_or_create_group(g["id"], g.get("label", g["id"]), kind="layer")

    for n in payload.get("nodes", []) or []:
        node = Node(id=n["id"], label=n.get("label", n["id"]), group=n.get("group"))
        graph.add_node(node)
        if node.group:
            if node.group not in graph.groups:
                graph.get_or_create_group(node.group, node.group, kind="layer")
            graph.groups[node.group].node_ids.append(node.id)

    for e in payload.get("edges", []) or []:
        if e["source"] not in graph.nodes or e["target"] not in graph.nodes:
            continue  # skip dangling references defensively
        graph.add_edge(Edge(
            id=f"e{len(graph.edges) + 1}",
            source=e["source"],
            target=e["target"],
            label=e.get("label"),
            style=e.get("style", "solid"),
            bidirectional=bool(e.get("bidirectional", False)),
        ))

    return graph


def extract_from_image(
    image_path: str,
    api_provider: str = "openai",
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    mock: bool = False,
) -> Graph:
    """Run the AI pre-processing extraction step on a diagram image.

    api_provider: "openai" | "anthropic"
    api_key: falls back to OPENAI_API_KEY / ANTHROPIC_API_KEY env vars
    model: defaults to "gpt-4o" for OpenAI or "claude-sonnet-4-5" for Anthropic
    mock: force the deterministic stub extractor (no network call)
    """
    api_key = api_key or os.environ.get(
        "OPENAI_API_KEY" if api_provider == "openai" else "ANTHROPIC_API_KEY"
    )

    if mock or not api_key:
        payload = _mock_extract(image_path)
    elif api_provider == "openai":
        payload = _call_openai(image_path, api_key, model or "gpt-4o")
    elif api_provider == "anthropic":
        payload = _call_anthropic(image_path, api_key, model or "claude-sonnet-4-5")
    else:
        raise ValueError(f"Unknown api_provider: {api_provider!r} (use 'openai' or 'anthropic')")

    return _payload_to_graph(payload)
