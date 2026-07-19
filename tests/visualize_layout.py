"""
Renders a simplified PNG preview of the computed layout (rectangles for
containers/nodes + lines for edges) purely to visually sanity-check that the
layered layout engine produces non-overlapping, readable positions before
trusting the generated drawio XML. This is NOT how the real icons look in
draw.io (those use the official AWS4/Azure stencils) -- it's a geometry
debug view only.
"""
import sys
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrow, Rectangle

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from diagram2drawio.enrichment import enrich_graph_with_icons  # noqa: E402
from diagram2drawio.layout.layered_layout import apply_layered_layout  # noqa: E402
from diagram2drawio.pipeline import load_graph  # noqa: E402

PROVIDER_COLOR = {"aws": "#FDECD4", "azure": "#D6E9FA", "generic": "#EEEEEE"}
PROVIDER_EDGE = {"aws": "#ED7100", "azure": "#0078D4", "generic": "#999999"}


def render(input_path: str, out_png: str):
    graph = load_graph(input_path)
    enrich_graph_with_icons(graph)
    layout = apply_layered_layout(graph)

    fig, ax = plt.subplots(figsize=(layout.canvas_width / 80, layout.canvas_height / 80))
    ax.set_xlim(0, layout.canvas_width)
    ax.set_ylim(0, layout.canvas_height)
    ax.invert_yaxis()
    ax.axis("off")
    ax.set_title(graph.title, fontsize=14, fontweight="bold", loc="left")

    abs_pos = {}
    for gid in layout.container_order:
        g = graph.groups[gid]
        ax.add_patch(Rectangle((g.x, g.y), g.width, g.height, fill=False, edgecolor="#999999", linestyle="--", linewidth=1.2))
        ax.text(g.x + 8, g.y + 14, g.label, fontsize=9, fontweight="bold", color="#666666")
        for nid in g.node_ids:
            n = graph.nodes[nid]
            ax_x, ax_y = g.x + n.x, g.y + n.y
            abs_pos[nid] = (ax_x + n.width / 2, ax_y + n.height / 2)
            color = PROVIDER_COLOR.get(n.provider, "#EEEEEE")
            edgecolor = PROVIDER_EDGE.get(n.provider, "#999999")
            ax.add_patch(Rectangle((ax_x, ax_y), n.width, n.height, facecolor=color, edgecolor=edgecolor, linewidth=1.5))
            ax.text(ax_x + n.width / 2, ax_y + n.height / 2, n.label, fontsize=7.5, ha="center", va="center", wrap=True)

    for e in graph.edges:
        if e.source not in abs_pos or e.target not in abs_pos:
            continue
        x1, y1 = abs_pos[e.source]
        x2, y2 = abs_pos[e.target]
        ax.annotate(
            "", xy=(x2, y2), xytext=(x1, y1),
            arrowprops=dict(arrowstyle="->", color="#555555", lw=0.8, shrinkA=15, shrinkB=15),
        )

    plt.tight_layout()
    plt.savefig(out_png, dpi=150)
    print(f"Saved {out_png}")


if __name__ == "__main__":
    for name in ["ecommerce_aws.mmd", "three_tier_azure.puml", "hybrid_no_groups.mmd"]:
        render(str(ROOT / "tests" / "sample_diagrams" / name), str(ROOT / "examples" / (Path(name).stem + "_preview.png")))
