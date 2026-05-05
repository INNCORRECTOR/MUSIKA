"""
Convert raster images under a directory tree to WebP.

Usage:
  python scripts/convert_images_to_webp.py
  python scripts/convert_images_to_webp.py --root static --quality 82
  python scripts/convert_images_to_webp.py --root static --delete-originals

Requires: pip install Pillow
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image

# Project root (parent of scripts/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tif", ".tiff"})


def _prepare_image_for_webp(im: Image.Image) -> Image.Image:
    """Normalize mode so WebP save is reliable (alpha, palette, CMYK, etc.)."""
    if im.mode in ("RGBA", "LA"):
        return im
    if im.mode == "P":
        if "transparency" in im.info:
            return im.convert("RGBA")
        return im.convert("RGB")
    if im.mode == "RGB":
        return im
    return im.convert("RGB")


def convert_images_to_webp(
    root: Path | str,
    *,
    quality: int = 85,
    delete_originals: bool = False,
    skip_existing: bool = True,
    extensions: frozenset[str] | None = None,
) -> list[tuple[Path, Path]]:
    """
    Walk ``root`` and write a sibling ``.webp`` for each matching image.

    Returns a list of (source_path, webp_path) for files that were written.
    Skips sources that already have ``.webp`` extension. Animated GIFs are
    converted using the first frame only.

    :param root: Directory to scan recursively.
    :param quality: WebP quality 1–100 (lossy); ignored for RGBA if using lossless.
    :param delete_originals: Remove the source file after a successful write.
    :param skip_existing: Do not overwrite an existing ``.webp`` of the same name.
    :param extensions: Lowercase extensions to include (including dot). Defaults to common raster types.
    """
    root_path = Path(root).resolve()
    if not root_path.is_dir():
        raise NotADirectoryError(f"Not a directory: {root_path}")

    exts = extensions if extensions is not None else DEFAULT_EXTENSIONS
    converted: list[tuple[Path, Path]] = []

    for path in sorted(root_path.rglob("*")):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix == ".webp":
            continue
        if suffix not in exts:
            continue

        dest = path.with_suffix(".webp")
        if skip_existing and dest.exists():
            continue

        try:
            with Image.open(path) as im:
                im.load()
                if getattr(im, "is_animated", False):
                    im.seek(0)
                prepared = _prepare_image_for_webp(im)
                prepared.save(dest, "WEBP", quality=quality, method=6)
        except OSError:
            raise
        except Exception as exc:
            print(f"[skip] {path}: {exc}", file=sys.stderr)
            continue

        converted.append((path, dest))
        if delete_originals:
            path.unlink()

    return converted


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert images under a folder to WebP.")
    parser.add_argument(
        "--root",
        type=Path,
        default=PROJECT_ROOT / "static",
        help="Root directory to scan (default: project static/)",
    )
    parser.add_argument("--quality", type=int, default=85, help="WebP quality 1–100 (default: 85)")
    parser.add_argument(
        "--delete-originals",
        action="store_true",
        help="Remove source files after successful conversion (destructive)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing .webp files (default: skip if dest exists)",
    )
    args = parser.parse_args()

    if not (1 <= args.quality <= 100):
        print("quality must be between 1 and 100", file=sys.stderr)
        return 2

    pairs = convert_images_to_webp(
        args.root,
        quality=args.quality,
        delete_originals=args.delete_originals,
        skip_existing=not args.overwrite,
    )
    for src, dst in pairs:
        print(f"{src} -> {dst}")
    print(f"Done. {len(pairs)} file(s) converted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
