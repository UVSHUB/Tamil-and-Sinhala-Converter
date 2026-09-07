"""CLI entry point for command-line translation."""

import argparse
import sys
from sinhala_tamil_converter.converter import SinhalaTamilConverter


def main() -> None:
    """Run CLI argument parser and translation execution."""
    parser = argparse.ArgumentParser(
        prog="st-convert",
        description="Convert / Translate text between Sinhala and Tamil",
    )
    parser.add_argument("text", type=str, help="Text to translate")
    parser.add_argument(
        "--source",
        "-s",
        type=str,
        default="auto",
        choices=["sinhala", "tamil", "auto"],
        help="Source language (default: auto)",
    )
    parser.add_argument(
        "--target",
        "-t",
        type=str,
        default=None,
        choices=["sinhala", "tamil"],
        help="Target language (defaults to opposite of source)",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.2,
        help="Model temperature (default: 0.2)",
    )

    args = parser.parse_args()
    try:
        converter = SinhalaTamilConverter()
        result = converter.translate(
            args.text,
            source=args.source,
            target=args.target,
            temperature=args.temperature,
        )
        print(result.text)
    except Exception as err:
        sys.stderr.write(f"Error: {err}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
