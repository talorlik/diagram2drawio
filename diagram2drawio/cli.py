"""
Command-line entry point.

Examples:
    python -m diagram2drawio.cli convert -i architecture.mmd -o architecture.drawio
    python -m diagram2drawio.cli convert -i diagram.png -o architecture.drawio --ai-provider anthropic
    python -m diagram2drawio.cli convert -i spec.puml -o architecture.drawio --provider azure
"""
from __future__ import annotations

import argparse
import sys

from .pipeline import convert


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="diagram2drawio", description="Convert diagrams/specs into editable .drawio files")
    sub = parser.add_subparsers(dest="command", required=True)

    p_convert = sub.add_parser("convert", help="Run the full conversion pipeline")
    p_convert.add_argument("-i", "--input", required=True, help="Path to input file: image (.png/.jpg), Mermaid (.mmd), or PlantUML (.puml)")
    p_convert.add_argument("-o", "--output", required=True, help="Path to write the resulting .drawio file")
    p_convert.add_argument("--input-format", choices=["image", "mermaid", "plantuml"], default=None,
                            help="Force the input format instead of auto-detecting from extension/content")
    p_convert.add_argument("--provider", choices=["auto", "aws", "azure"], default="auto",
                            help="Icon set to use. 'auto' infers AWS vs Azure per-node from labels (default)")
    p_convert.add_argument("--ai-provider", choices=["openai", "anthropic"], default="openai",
                            help="Vision LLM used for image inputs (default: openai)")
    p_convert.add_argument("--api-key", default=None,
                            help="API key for the AI provider (falls back to OPENAI_API_KEY/ANTHROPIC_API_KEY env vars)")
    p_convert.add_argument("--mock", action="store_true",
                            help="Use a deterministic mock extractor for image inputs instead of calling a real API (testing/demo only)")

    args = parser.parse_args(argv)

    if args.command == "convert":
        try:
            out = convert(
                args.input,
                args.output,
                input_format=args.input_format,
                provider=args.provider,
                ai_provider=args.ai_provider,
                api_key=args.api_key,
                mock_image_extraction=args.mock,
            )
        except Exception as exc:  # noqa: BLE001 -- surface a clean CLI error
            print(f"Conversion failed: {exc}", file=sys.stderr)
            return 1
        print(f"Wrote {out}")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
