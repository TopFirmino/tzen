"""Offline testcase documentation: python -m tzen docs --config board.toml."""
import argparse
from pathlib import Path

from .config import Settings
from .declarations import load_declarations, documentation_record, write_documentation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    docs = subcommands.add_parser("docs", help="Export Python declarations without opening a transport")
    docs.add_argument("--config", type=Path, required=True)
    docs.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    settings = Settings.load(args.config.resolve())
    declarations, _ = load_declarations(settings.companion_paths)
    write_documentation(args.output, [documentation_record(d) for d in declarations.values()], verified=False)
    print(f"Exported {len(declarations)} testcase declarations to {args.output} (offline, not verified against firmware)")


if __name__ == "__main__":
    main()
