"""
What: Create a small source/context ZIP for browser-chat handoff.
Run:  python scripts/make_context_zip.py
Deps: Python standard library only.

The archive includes every ordinary project file that is not secret, generated,
dependency-managed, or individually huge. It exits non-zero if the final archive
is larger than 10 MB by default. A manifest is written inside the ZIP so another
LLM can see what was included and why anything was skipped.
"""

from __future__ import annotations

import argparse
from collections import Counter
import logging
import zipfile
from datetime import datetime
from pathlib import Path


LOGGER = logging.getLogger("context-zip")
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MAX_BYTES = 10 * 1024 * 1024
DEFAULT_MAX_FILE_BYTES = 5 * 1024 * 1024
OUTPUT_DIR = PROJECT_ROOT / "tmp" / "context_zips"

EXCLUDED_DIR_NAMES = {
    ".git",
    ".firebase",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".solcx",
    ".venv",
    "__pycache__",
    "artifacts",
    "build",
    "cache",
    "coverage",
    "dist",
    "log",
    "logs",
    "node_modules",
    "tmp",
}
EXCLUDED_FILE_NAMES = {
    ".DS_Store",
    ".env",
    ".env.local",
    "config.local.json",
    "firebase-debug.log",
}
EXCLUDED_SUFFIXES = {
    ".log",
    ".pyc",
    ".zip",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Create context ZIP")
    parser.add_argument("--max-mb", type=float, default=10.0)
    parser.add_argument(
        "--max-file-mb",
        type=float,
        default=5.0,
        help="Skip individual files above this size before compression.",
    )
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    max_bytes = int(args.max_mb * 1024 * 1024)
    max_file_bytes = int(args.max_file_mb * 1024 * 1024)
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_path = output_dir / f"foreign_intelligence_context_{stamp}.zip"
    files, skipped = collect_context_files(max_file_bytes=max_file_bytes)
    assert files, "No files selected for archive"

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(PROJECT_ROOT))
        archive.writestr(
            "context_zip_manifest.txt",
            build_manifest(files=files, skipped=skipped, max_file_bytes=max_file_bytes),
        )

    size = zip_path.stat().st_size
    LOGGER.info("zip_path=%s", zip_path)
    LOGGER.info("file_count=%s", len(files))
    LOGGER.info("skipped_count=%s", len(skipped))
    LOGGER.info("size_bytes=%s", size)
    LOGGER.info("size_mb=%.2f", size / 1024 / 1024)
    assert size <= max_bytes, (
        f"Archive is larger than limit: {size} bytes > {max_bytes} bytes"
    )


def collect_context_files(max_file_bytes: int) -> tuple[list[Path], list[tuple[Path, str]]]:
    selected: list[Path] = []
    skipped: list[tuple[Path, str]] = []
    for path in sorted(PROJECT_ROOT.rglob("*")):
        if path.is_dir():
            continue
        relative_parts = path.relative_to(PROJECT_ROOT).parts
        if any(part in EXCLUDED_DIR_NAMES for part in relative_parts[:-1]):
            skipped.append((path, "excluded directory"))
            continue
        if path.name in EXCLUDED_FILE_NAMES:
            skipped.append((path, "excluded filename"))
            continue
        if path.suffix in EXCLUDED_SUFFIXES:
            skipped.append((path, "excluded suffix"))
            continue
        if path.stat().st_size > max_file_bytes:
            skipped.append((path, f"larger than {max_file_bytes} bytes"))
            continue
        selected.append(path)
    return selected, skipped


def build_manifest(
    files: list[Path],
    skipped: list[tuple[Path, str]],
    max_file_bytes: int,
) -> str:
    skipped_counts = Counter(reason for _, reason in skipped)
    lines = [
        "Context ZIP manifest",
        f"project_root={PROJECT_ROOT}",
        f"max_file_bytes={max_file_bytes}",
        "",
        "Included files:",
    ]
    for path in files:
        relative_path = path.relative_to(PROJECT_ROOT)
        lines.append(f"- {relative_path} ({path.stat().st_size} bytes)")

    lines.extend(["", "Skipped files:"])
    if not skipped:
        lines.append("- none")
    else:
        lines.append(f"- total skipped: {len(skipped)}")
        for reason, count in sorted(skipped_counts.items()):
            lines.append(f"- {reason}: {count}")
        lines.append("")
        lines.append("First skipped examples:")
        for path, reason in skipped[:50]:
            relative_path = path.relative_to(PROJECT_ROOT)
            lines.append(f"- {relative_path}: {reason}")
        if len(skipped) > 50:
            lines.append(f"- ... {len(skipped) - 50} more skipped files omitted")

    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
