"""
End-to-end orchestration: input (image | mermaid | plantuml) -> AI/parser
pre-processing -> icon enrichment -> layered layout -> drawio XML export.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from .enrichment import enrich_graph_with_icons
from .export.drawio_writer import write_drawio_file
from .extraction.image_extractor import extract_from_image
from .layout.layered_layout import apply_layered_layout
from .models import Graph
from .parsers.mermaid_parser import parse_mermaid
from .parsers.plantuml_parser import parse_plantuml

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}


def detect_input_format(input_path: str, explicit_format: Optional[str] = None) -> str:
    if explicit_format:
        return explicit_format
    suffix = Path(input_path).suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        return "image"
    if suffix in (".puml", ".plantuml", ".pu"):
        return "plantuml"
    if suffix in (".mmd", ".mermaid"):
        return "mermaid"
    # Text file with ambiguous extension -- sniff content.
    text = Path(input_path).read_text(encoding="utf-8", errors="ignore")
    return _sniff_text_format(text)


def _sniff_text_format(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("@startuml") or "@startuml" in stripped:
        return "plantuml"
    if stripped.startswith(("flowchart", "graph ")) or "-->" in stripped or "subgraph" in stripped:
        return "mermaid"
    return "mermaid"  # default best guess for unrecognized text specs


def load_graph(
    input_path: str,
    input_format: Optional[str] = None,
    provider: str = "auto",
    ai_provider: str = "openai",
    api_key: Optional[str] = None,
    mock_image_extraction: bool = False,
) -> Graph:
    fmt = detect_input_format(input_path, input_format)

    if fmt == "image":
        graph = extract_from_image(input_path, api_provider=ai_provider, api_key=api_key, mock=mock_image_extraction)
    elif fmt == "plantuml":
        graph = parse_plantuml(Path(input_path).read_text(encoding="utf-8"))
    elif fmt == "mermaid":
        graph = parse_mermaid(Path(input_path).read_text(encoding="utf-8"))
    else:
        raise ValueError(f"Unsupported input format: {fmt!r}")

    if not graph.title or graph.title == "Architecture Diagram":
        graph.title = Path(input_path).stem.replace("_", " ").replace("-", " ").title()

    graph.default_provider = provider
    return graph


def convert(
    input_path: str,
    output_path: str,
    input_format: Optional[str] = None,
    provider: str = "auto",
    ai_provider: str = "openai",
    api_key: Optional[str] = None,
    mock_image_extraction: bool = False,
) -> str:
    """Run the full pipeline and write the resulting .drawio file.

    Returns the output path. Raises on any stage failure (parse error,
    unresolvable AI response, invalid XML) rather than silently producing a
    broken file.
    """
    graph = load_graph(
        input_path,
        input_format=input_format,
        provider=provider,
        ai_provider=ai_provider,
        api_key=api_key,
        mock_image_extraction=mock_image_extraction,
    )
    enrich_graph_with_icons(graph, provider=provider)
    layout = apply_layered_layout(graph)
    return write_drawio_file(graph, layout, output_path)
