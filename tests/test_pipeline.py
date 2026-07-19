"""
Smoke tests for the full pipeline. Run with: python tests/test_pipeline.py
Not pytest-based on purpose -- zero extra dependencies needed to verify the
generated .drawio files are well-formed and structurally sane.
"""
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from diagram2drawio.pipeline import convert, load_graph  # noqa: E402
from diagram2drawio.enrichment import enrich_graph_with_icons  # noqa: E402

SAMPLES_DIR = ROOT / "tests" / "sample_diagrams"
OUT_DIR = ROOT / "examples"
OUT_DIR.mkdir(exist_ok=True)


def check_drawio_structure(path: Path, min_nodes: int, min_edges: int):
    tree = ET.parse(path)
    root = tree.getroot()
    assert root.tag == "mxfile", f"root tag is {root.tag}, expected mxfile"
    model = root.find("./diagram/mxGraphModel")
    assert model is not None, "missing mxGraphModel"
    cells = model.findall(".//mxCell")
    vertices = [c for c in cells if c.get("vertex") == "1"]
    edges = [c for c in cells if c.get("edge") == "1"]
    node_vertices = [c for c in vertices if c.get("id") not in ("title", "subtitle") and not c.get("id", "").startswith("grp_")]
    print(f"  {path.name}: {len(vertices)} vertices ({len(node_vertices)} nodes), {len(edges)} edges")
    assert len(node_vertices) >= min_nodes, f"expected >= {min_nodes} nodes, got {len(node_vertices)}"
    assert len(edges) >= min_edges, f"expected >= {min_edges} edges, got {len(edges)}"
    # Every edge source/target must reference a vertex id that exists.
    vertex_ids = {c.get("id") for c in vertices}
    for e in edges:
        assert e.get("source") in vertex_ids, f"dangling edge source {e.get('source')}"
        assert e.get("target") in vertex_ids, f"dangling edge target {e.get('target')}"
    return vertices, edges


def run_case(name, input_file, min_nodes, min_edges, **kwargs):
    print(f"\n=== {name} ===")
    out_path = OUT_DIR / f"{input_file.stem}.drawio"
    convert(str(SAMPLES_DIR / input_file.name), str(out_path), **kwargs)
    check_drawio_structure(out_path, min_nodes, min_edges)
    print(f"  OK -> {out_path}")


def main():
    run_case("Mermaid AWS e-commerce (explicit subgraphs)", Path("ecommerce_aws.mmd"), min_nodes=19, min_edges=20)
    run_case("PlantUML Azure three-tier (explicit packages)", Path("three_tier_azure.puml"), min_nodes=15, min_edges=15)
    run_case("Mermaid hybrid, no explicit groups (auto layering)", Path("hybrid_no_groups.mmd"), min_nodes=7, min_edges=7)

    # Mock image extraction path (no API key needed).
    print("\n=== Mock image extraction ===")
    fake_image = OUT_DIR / "mock_input.png"
    fake_image.write_bytes(b"\x89PNG\r\n\x1a\n")  # minimal placeholder bytes, content unused in mock mode
    out_path = OUT_DIR / "mock_input.drawio"
    convert(str(fake_image), str(out_path), mock_image_extraction=True)
    check_drawio_structure(out_path, min_nodes=5, min_edges=4)
    print(f"  OK -> {out_path}")

    # Icon resolution sanity check: verify AWS vs Azure labels resolve to
    # the correct provider and a real service-specific shape, not a generic
    # fallback box.
    print("\n=== Icon resolution spot-check ===")
    graph = load_graph(str(SAMPLES_DIR / "ecommerce_aws.mmd"))
    enrich_graph_with_icons(graph)
    checks = {
        "CF": ("aws", "cloudfront"), "OrdersDB": ("aws", "dynamodb"),
        "CatalogDB": ("aws", "rds"), "WAFR": ("aws", "waf"),
    }
    for node_id, (exp_provider, exp_icon) in checks.items():
        node = graph.nodes[node_id]
        assert node.provider == exp_provider, f"{node_id}: expected provider {exp_provider}, got {node.provider}"
        assert node.icon_key == exp_icon, f"{node_id}: expected icon {exp_icon}, got {node.icon_key}"
        print(f"  {node_id} ({node.label}) -> provider={node.provider}, icon={node.icon_key}, layer={node.layer}")

    print("\nAll pipeline smoke tests passed.")


if __name__ == "__main__":
    main()
