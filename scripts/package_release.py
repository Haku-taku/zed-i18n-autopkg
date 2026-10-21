#!/usr/bin/env python3
"""Turn one upstream zed-i18n release into an Arch Linux package release.

Input is a directory holding the Linux tarballs downloaded from an upstream
``LI-NA/zed-i18n`` release. Output is the same directory, now also holding one
``*-pkgdir.tar.gz`` staging tree per architecture plus the ``PKGBUILD`` whose
``sha256sums`` are rendered from those exact trees.

Nothing here compiles: upstream already built the editor, and the staging step
only relocates the bundle into the FHS layout the official Arch package owns.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from tools.zed_i18n.arch import (  # noqa: E402
    PKGBUILD_ASSET_NAME,
    PKGBUILD_TEMPLATE,
    SUPPORTED_ARCHES,
    arch_asset_name,
    build_release_arch,
    render_pkgbuild,
    sha256_file,
)

# `v<zed-version>-i18n.<revision>`. The Zed version is load-bearing rather than
# cosmetic: zed-i18n addresses every translation by byte offset in one pinned
# Zed revision, so a package built for a different Zed version would mis-apply
# them. Taking it from the tag keeps pkgver and the pinned revision in step.
TAG_PATTERN = re.compile(r"^v(?P<version>\d+\.\d+\.\d+)-i18n\.(?P<revision>\d+)$")


def parse_tag(tag: str) -> tuple[str, int]:
    match = TAG_PATTERN.match(tag)
    if match is None:
        raise SystemExit(f"not a zed-i18n release tag: {tag!r}")
    return match.group("version"), int(match.group("revision"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist-dir", required=True, type=Path)
    parser.add_argument("--release-tag", required=True)
    parser.add_argument(
        "--repository",
        required=True,
        help="owner/name of the repository that will host the staging trees",
    )
    parser.add_argument("--max-workers", type=int)
    args = parser.parse_args()

    dist_dir: Path = args.dist_dir.resolve()
    if not dist_dir.is_dir():
        raise SystemExit(f"no such directory: {dist_dir}")

    pkgver, i18nrev = parse_tag(args.release_tag)

    trees = build_release_arch(dist_dir, max_workers=args.max_workers)
    if not trees:
        raise SystemExit(
            f"no Linux release tarballs in {dist_dir}; expected "
            f"{arch_asset_name(None, 'x86_64').replace('-pkgdir', '')} and its aarch64 twin"
        )

    # Re-hash the trees rather than trusting anything already written, so the
    # digests in the PKGBUILD describe the bytes published beside it.
    digests: dict[str, str] = {}
    for arch in SUPPORTED_ARCHES:
        tree = dist_dir / arch_asset_name(None, arch)
        if not tree.is_file():
            raise SystemExit(f"missing staging tree for {arch}: {tree}")
        digests[arch] = sha256_file(tree)

    rendered = render_pkgbuild(
        PKGBUILD_TEMPLATE.read_text(encoding="utf-8"),
        pkgver=pkgver,
        i18nrev=i18nrev,
        repository=args.repository,
        digests=digests,
    )
    (dist_dir / PKGBUILD_ASSET_NAME).write_text(rendered, encoding="utf-8")

    print(f"pkgver={pkgver} _i18nrev={i18nrev}")
    for arch in SUPPORTED_ARCHES:
        print(f"{arch}: {digests[arch]}")
    print(f"wrote {dist_dir / PKGBUILD_ASSET_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
