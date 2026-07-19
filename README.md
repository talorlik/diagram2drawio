# diagram2drawio

Automated architecture conversion pipeline: turn a **diagram image**, a **Mermaid** flowchart, or a **PlantUML** component/deployment spec into an **editable, enterprise-ready `.drawio` file** — with real AWS4 / Azure stencil icons, layer-grouped containers, and orthogonal-routed connections that open cleanly in [diagrams.net](https://app.diagrams.net) / draw.io Desktop.

```
 Image (.png/.jpg)  ──┐
 Mermaid (.mmd)       ├─▶  Parse / AI-extract  ─▶  Canonical Graph (IR)  ─▶  Icon enrichment  ─▶  Layered layout  ─▶  draw.io XML writer  ─▶  .drawio
 PlantUML (.puml)    ─┘
```

## What it does

1. **Ingests** an architecture description in one of three forms:
   - A **diagram image** (screenshot, exported PNG/JPG of a whiteboard or slide) — pre-processed by a **vision LLM** (OpenAI GPT-4o or Anthropic Claude) that extracts nodes, connections, groups and layout intent as structured JSON.
   - A **Mermaid** flowchart/graph spec (`.mmd`), including subgraphs, labeled/typed edges, and shape hints.
   - A **PlantUML** component/deployment spec (`.puml`), including nested containers (`package`/`node`/`rectangle` blocks) and relationship labels.
2. **Normalizes** everything into one canonical intermediate representation (nodes, edges, groups) regardless of source format.
3. **Resolves AWS/Azure icons** for each node from free-text labels (e.g. "Orders DynamoDB table" → `aws/dynamodb`) using a keyword-matching engine backed by editable JSON icon libraries, so icon sets stay **consistent** across a diagram (and across diagrams) instead of ad hoc boxes.
4. **Lays the diagram out** in horizontal, labeled layers (Edge → Network → Security → Compute → Messaging → Data → Analytics → ML → Monitoring), the way enterprise architecture docs are usually drawn, with automatic grid-packing and light edge-crossing reduction — whether or not the source spec had explicit groups.
5. **Writes valid draw.io XML** (`mxfile` / `mxGraphModel`) using the official `mxgraph.aws4.*` and `mxgraph.azure.*` stencil shapes, validates it, and saves it as a `.drawio` file you can double-click open and keep editing.

## Project layout

```
diagram2drawio/
├── diagram2drawio/
│   ├── models.py                 # Canonical IR: Node, Edge, Group, Graph
│   ├── pipeline.py                # convert() orchestrator + format auto-detection
│   ├── cli.py                     # `python -m diagram2drawio.cli convert ...`
│   ├── parsers/
│   │   ├── mermaid_parser.py      # Mermaid flowchart/graph → Graph
│   │   └── plantuml_parser.py     # PlantUML component/deployment → Graph
│   ├── extraction/
│   │   └── image_extractor.py     # Vision LLM (OpenAI/Anthropic) image → Graph, + mock mode
│   ├── enrichment.py               # Resolves provider/icon/layer/style per node
│   ├── icons/
│   │   ├── aws_icons.json          # ~40 AWS services: keywords, layer, category, resIcon
│   │   ├── azure_icons.json        # ~35 Azure services: keywords, layer, category, shape
│   │   └── icon_library.py         # Keyword-match resolution engine + style builder
│   ├── layout/
│   │   └── layered_layout.py       # Layer-grouped auto-layout engine
│   └── export/
│       └── drawio_writer.py        # Canonical graph + layout → validated .drawio XML
├── tests/
│   ├── sample_diagrams/            # 3 complex example inputs (AWS, Azure, hybrid)
│   ├── test_pipeline.py            # Smoke tests — run this to sanity check the install
│   └── visualize_layout.py         # Optional matplotlib debug preview renderer
├── examples/                       # Generated .drawio outputs + preview PNGs from the samples
├── requirements.txt
└── README.md
```

## Installation

```bash
cd diagram2drawio
pip install -r requirements.txt
```

The core pipeline only needs `requests` (used by the AI image-extraction HTTP calls). No API key is required to convert Mermaid or PlantUML text specs — those are parsed locally with no network calls.

For image inputs with real AI extraction, set one of:

```bash
export OPENAI_API_KEY="sk-..."       # for --ai-provider openai (default)
export ANTHROPIC_API_KEY="sk-ant-..." # for --ai-provider anthropic
```

If neither key is set (or you pass `--mock`), image inputs fall back to a deterministic **mock extractor** so you can exercise the full pipeline without any API access.

## CLI usage

```bash
# Mermaid flowchart -> AWS-styled .drawio
python -m diagram2drawio.cli convert -i architecture.mmd -o architecture.drawio

# PlantUML spec, force Azure icon set
python -m diagram2drawio.cli convert -i spec.puml -o architecture.drawio --provider azure

# Diagram image, extract with Claude vision
python -m diagram2drawio.cli convert -i whiteboard.png -o architecture.drawio --ai-provider anthropic

# Diagram image, no API key available -> deterministic mock extraction (demo/testing)
python -m diagram2drawio.cli convert -i whiteboard.png -o architecture.drawio --mock
```

Flags:

| Flag | Values | Description |
|---|---|---|
| `-i, --input` | path | Image (`.png`/`.jpg`), Mermaid (`.mmd`), or PlantUML (`.puml`) |
| `-o, --output` | path | Where to write the `.drawio` file |
| `--input-format` | `image` \| `mermaid` \| `plantuml` | Force format instead of auto-detecting from extension/content |
| `--provider` | `auto` \| `aws` \| `azure` | Icon set. `auto` (default) infers AWS vs Azure **per node** from its label, so a single diagram can mix both clouds correctly |
| `--ai-provider` | `openai` \| `anthropic` | Vision LLM for image inputs |
| `--api-key` | string | Overrides `OPENAI_API_KEY`/`ANTHROPIC_API_KEY` |
| `--mock` | flag | Skip real AI calls for image inputs; use a deterministic 5-node sample graph |

Or call it from Python directly:

```python
from diagram2drawio import convert
convert("architecture.mmd", "architecture.drawio", provider="auto")
```

## How the AI pre-processing step works (image inputs)

`extraction/image_extractor.py` sends the image, base64-encoded, to a vision-capable LLM with a strict JSON-schema system prompt asking for `nodes` (id, label, provider hint, group), `edges` (source, target, label), and `groups` (label, member node ids) — i.e. the same shape the Mermaid/PlantUML parsers produce, so every input format converges on one canonical `Graph` before layout/export. Supported providers:

- **OpenAI** — `gpt-4o` via `/v1/chat/completions` with `response_format={"type": "json_object"}`
- **Anthropic** — Claude via `/v1/messages` with vision content blocks

If no API key is available, `_mock_extract()` returns a fixed 5-node sample graph so the rest of the pipeline (icon resolution, layout, XML export) can be exercised end-to-end without any network access — useful for CI, demos, or offline development.

## How icon resolution works

`icons/icon_library.py` matches each node's free-text label against keyword lists in `icons/aws_icons.json` / `icons/azure_icons.json` (longest-keyword-match wins), returning:

- a **provider** (`aws`, `azure`, or `generic` for actors/unrecognized nodes)
- an architecture **layer** (edge, network, security, compute, messaging, data, analytics, ml, monitoring, other) — used to decide which horizontal band the node lands in during layout
- a ready-to-use draw.io **style string** using the correct AWS4/Azure stencil convention

AWS4 stencils have two distinct icon patterns that must not be mixed (mixing them is the most common cause of blank/broken icons):

| Pattern | Style | `strokeColor` | Used for |
|---|---|---|---|
| Service-level (framed) | `shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.<name>` | `#ffffff` (required) | Most services — Lambda, S3, RDS, DynamoDB, ECS, EKS, etc. |
| Resource-level (standalone) | `shape=mxgraph.aws4.<name>` | `none` (required) | Sub-resources — VPC, Subnet, Internet Gateway, NAT Gateway |

`icon_library.py` picks the right pattern per entry via an `"icon_pattern": "resource"` flag in `aws_icons.json` (omit the field for the default framed pattern). Azure stencils use a single flat `shape=mxgraph.azure.<name>` pattern with `strokeColor=none`.

### Extending or correcting the icon libraries

Icon names are **data, not code** — draw.io's `mxgraph.aws4.*`/`mxgraph.azure.*` shape library isn't officially documented and naming has occasionally shifted across draw.io releases, so if any icon renders as a blank/generic square in your draw.io version:

1. Open draw.io, use **Edit Style** on any shape from the built-in AWS/Azure shape search to find the exact current `resIcon`/`shape` name.
2. Update the corresponding entry's `res_icon` value in `diagram2drawio/icons/aws_icons.json` or `azure_icons.json` — no code changes needed.
3. Re-run `python3 tests/test_pipeline.py` to confirm the JSON is still valid and the pipeline still runs.

To add a new service, add an entry with `key`, `label`, `layer`, `category`, `res_icon`, and `keywords` (and `icon_pattern: "resource"` if it's a standalone/resource-level shape). The AWS icon names in this project were cross-checked against the shape names extracted from draw.io's own `Sidebar-AWS4.js` source (via the [vidanov/aws-architecture-diagram-skill](https://github.com/vidanov/aws-architecture-diagram-skill) reference tables) and the [draw.io AWS diagrams docs](https://www.drawio.com/docs/diagram-types/aws-diagrams/); Azure names were cross-checked against the [ClaudePluginHub drawio-diagramming XML generation reference](https://www.claudepluginhub.com/skills/markus41-drawio-diagramming-plugins-drawio-diagramming/xml-generation) and the [draw.io Azure diagrams docs](https://www.drawio.com/docs/diagram-types/azure-diagrams/). A handful of AWS icons (e.g. `xray`, `autoscaling`, a couple of niche ones) were not independently re-verified against the extracted source list — treat those as best-effort and correct via step 1–2 above if needed.

## How the layered layout works

`layout/layered_layout.py` builds an ordered set of horizontal "lanes" (containers), either from:

- **explicit groups** in the source (Mermaid `subgraph`, PlantUML `package`/`node` blocks) — ordered by each group's average architecture-layer rank, or
- **synthesized canonical layers** when the source has no explicit grouping — nodes are auto-assigned a layer from their resolved icon metadata (or regex fallback for generic nodes like "User"/"Database"/"Queue").

Within each lane, nodes are grid-packed (max 6 per row) and lightly reordered by barycenter of their connections to the previous lane, to reduce edge crossings — the same general approach used in Sugiyama-style layered graph drawing. Each lane is rendered as a labeled, dashed-border container in the final XML.

## Output format

`export/drawio_writer.py` produces a standard `mxfile > diagram > mxGraphModel > root` document: a title/subtitle text cell, one container `mxCell` per layer with nodes parented to it (so dragging the container in draw.io moves its children), and edge `mxCell`s using `orthogonalEdgeStyle` routing. The XML is parsed with `xml.etree.ElementTree` before being written to catch malformed output before it reaches disk.

## Try it / see it work

Three complex sample inputs are included and already converted in `examples/`:

- `tests/sample_diagrams/ecommerce_aws.mmd` — 19-node AWS e-commerce architecture, 6 layers (Edge, Network, Compute, Messaging, Data, Observability) → `examples/ecommerce_aws.drawio`
- `tests/sample_diagrams/three_tier_azure.puml` — 16-node Azure three-tier architecture, 6 layers → `examples/three_tier_azure.drawio`
- `tests/sample_diagrams/hybrid_no_groups.mmd` — 9-node **mixed AWS+Azure** diagram with no explicit grouping, demonstrating automatic per-node provider detection and layer inference → `examples/hybrid_no_groups.drawio`

Open any of the `.drawio` files in [app.diagrams.net](https://app.diagrams.net) (File → Open From → Device) to see the result, or view the corresponding `*_preview.png` for a quick look without opening draw.io.

Run the smoke tests yourself:

```bash
python3 tests/test_pipeline.py
```

## Automation integration (Make.com / n8n)

The CLI is a plain subprocess with a clean exit code (`0` success, `1` failure) and prints the output path on success, so it drops into existing automation stacks without a wrapper:

- **Make.com** — use an *SSH*/*Shell* module (or a Custom App calling a small HTTP wrapper around `diagram2drawio.pipeline.convert`) triggered by a "watch new file" module on a Drive/S3 folder; pass the uploaded diagram path as input, write the `.drawio` output back to the same storage, and route the module's output path into your next automation step (e.g. auto-attach to a Notion/Confluence page).
- **n8n** — an `Execute Command` node running `python -m diagram2drawio.cli convert -i {{ $json.inputPath }} -o {{ $json.outputPath }} --provider auto`, chained after a Trigger node (webhook, file watcher, or Slack/email attachment), with the API keys set as n8n environment variables/credentials rather than passed on the command line.
- For either tool, prefer calling `diagram2drawio.pipeline.convert()` directly from a small FastAPI/Flask wrapper if you want structured JSON responses (node/edge counts, warnings) instead of parsing CLI stdout.

## Known limitations / honesty notes

- Icon `resIcon`/`shape` names are **config-driven** (see "Extending or correcting the icon libraries" above) precisely because draw.io's shape library naming isn't officially documented and has shifted across releases — most entries here were cross-checked against extracted-from-source reference tables, but treat any specific icon as verify-before-trusting in your exact draw.io version, especially after a draw.io update.
- The Mermaid/PlantUML parsers are regex-based and cover the common flowchart/component syntax used in architecture docs; highly unusual or exotic syntax variants may not parse.
- Image extraction quality depends entirely on the underlying vision LLM's read of the source image; dense or low-resolution diagrams may need a manual touch-up pass in draw.io after conversion.
