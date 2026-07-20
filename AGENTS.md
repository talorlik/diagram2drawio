# AGENTS.md — diagram2drawio

Guidance for AI coding agents working in this repository.

## What this project is

Python pipeline that converts an architecture **diagram image**, **Mermaid** (`.mmd`), or **PlantUML** (`.puml`) into an editable **`.drawio`** file with AWS4/Azure stencil icons, layered containers, and orthogonal edges.

```
image | mermaid | plantuml  →  Graph (IR)  →  icon enrichment  →  layered layout  →  draw.io XML
```

Public API: `diagram2drawio.convert()` / `load_graph()`. CLI: `python -m diagram2drawio.cli convert ...`.

## Architecture (do not collapse stages)

| Stage | Module | Responsibility |
|---|---|---|
| IR | `diagram2drawio/models.py` | `Node`, `Edge`, `Group`, `Graph` — sole contract between stages |
| Parse / extract | `parsers/`, `extraction/image_extractor.py` | Produce a `Graph` only |
| Enrich | `enrichment.py` + `icons/` | Set `provider`, `icon_key`, `layer`, `style` on each node |
| Layout | `layout/layered_layout.py` | Positions; containers absolute, nodes relative to parent |
| Export | `export/drawio_writer.py` | Validated `mxfile` / `mxGraphModel` XML |

Keep stages decoupled: parsers must not know about draw.io styles; the writer must not re-resolve icons. New input formats should adapt to `Graph` and plug into `pipeline.load_graph()`.

## Code conventions

- Prefer `from __future__ import annotations` and stdlib + `requests` only in the core package. Do not add runtime deps without a strong reason (`matplotlib` stays optional/dev for `tests/visualize_layout.py`). Do not pull in `python-dotenv` — use `env.load_dotenv` (stdlib).
- Tests are intentional **non-pytest** smoke tests: `python3 tests/test_pipeline.py` (zero extra deps). Extend that file rather than introducing pytest unless asked.
- Prefer editing icon **data** over hardcoding shape names in Python. Service icons live in `icons/aws_icons.json` and `icons/azure_icons.json`.
- Raise on stage failure; do not write a broken `.drawio` silently (`pipeline.convert` documents this).

## Critical icon rules (easy to break)

AWS4 has two patterns; mixing them produces blank icons in draw.io:

1. **Service (default):** `shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.<name>` with `strokeColor=#ffffff`
2. **Resource:** `shape=mxgraph.aws4.<name>` with `strokeColor=none` — set `"icon_pattern": "resource"` on the JSON entry (VPC, subnet, IGW, NAT, etc.)

Azure: flat `shape=mxgraph.azure.<name>` with `strokeColor=none`.

Resolution: longest keyword match wins (`icon_library.resolve`). Prefer longer/more specific keywords when adding services to avoid false matches (e.g. `"aws batch"` not just `"batch"`).

New service entry fields: `key`, `label`, `layer`, `category`, `res_icon`, `keywords` (+ optional `icon_pattern`).

## Layout / XML contracts

- Layer order: edge → network → security → compute → messaging → data → analytics → ml → monitoring → other.
- Explicit source groups (Mermaid `subgraph`, PlantUML packages) win over synthesized layer bands; layout orders those groups by average layer rank of members.
- Node geometry is **relative to the parent container cell** (mxGraph convention). Do not write absolute node coordinates into XML unless the node is parented to the page root.
- Writer validates with `xml.etree.ElementTree` before write. Edge `source`/`target` must reference existing vertex ids.

## Parsers & image extraction

- Mermaid/PlantUML parsers are **regex-based subsets** for architecture docs — not full grammars. Silent-ignore exotic directives rather than expanding to a full language unless requested.
- Image path needs a vision API key or `--mock`. Keys resolve in order: `--api-key` → process env → gitignored project-root `.env` (via `env.load_dotenv`). Ship placeholders only in root `.env.example`; never real secrets. Mock path must keep working for offline/CI; never require network for Mermaid/PlantUML.
- Image extractor JSON schema must stay aligned with what `Graph` expects (nodes/edges/groups with consistent ids).

## How to verify

After any pipeline, parser, icon, layout, writer, or env-loading change, from the **repository root** (where `requirements.txt` lives):

```bash
pip install -r requirements.txt   # if needed
python3 tests/test_pipeline.py
```

That regenerates files under `examples/` and asserts structure (node/edge counts, no dangling edges, icon spot-checks, `.env` loading). Prefer `--mock` for image flows in automated checks.

## Where to change what

| Goal | Touch |
|---|---|
| Fix blank AWS/Azure icon | `icons/*_icons.json` (`res_icon` / `icon_pattern`) |
| Add a cloud service synonym | keywords in the matching JSON entry |
| New input format | new parser + `pipeline.detect_input_format` / `load_graph` |
| Layout spacing / layers | `layout/layered_layout.py` |
| XML / styling of containers/edges | `export/drawio_writer.py` |
| CLI flags | `cli.py` + `pipeline.convert` kwargs |
| `.env` discovery / parsing | `env.py` (keep stdlib-only); document keys in `.env.example` |

## Out of scope / avoid

- Do not invent undocumented draw.io shape names; verify against draw.io Edit Style or known AWS4/Azure sidebar sources when changing `res_icon`.
- Do not put API keys in code, sample files, or `.env.example`; use a local `.env` / env vars / `--api-key`. Keep `.env` gitignored.
- Do not rewrite parsers into full Mermaid/PlantUML engines unless the task explicitly requires it.
- Keep README and this file aligned if you change CLI flags, pipeline stages, icon JSON schema, or how API keys are loaded.
