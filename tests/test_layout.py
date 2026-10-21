"""The staged tree is the package's contract with the official Arch layout.

Every assertion here is a path the official ``zed`` package owns, so a rename in
``arch.py`` that this test does not catch would ship a package that installs
beside ``zed`` instead of replacing it.

The bundle is synthetic: staging never reads the payload, only the member names,
so a 200 MB release tarball would test exactly the same code slower.
"""

from __future__ import annotations

import io
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from tools.zed_i18n.arch import (  # noqa: E402
    COMPLETION_TARGETS,
    build_arch_from_tarball,
    render_metainfo,
)

# Members the staging step expects to find in an upstream Linux bundle, before
# it drops `lib/` and `licenses.md` and relocates the rest.
BUNDLE_MEMBERS = {
    "zed.app/bin/zed": b"#!/bin/sh\nexit 0\n",
    "zed.app/libexec/zed-editor": b"#!/bin/sh\nexit 0\n",
    "zed.app/lib/libfoo.so": b"dropped\n",
    "zed.app/licenses.md": b"dropped\n",
    "zed.app/share/applications/dev.zed.Zed.desktop": (
        b"[Desktop Entry]\nName=Zed\nExec=zed %F\nIcon=zed\n"
    ),
    "zed.app/share/icons/hicolor/256x256/apps/zed.png": b"PNG",
}

EXPECTED_TREE = {
    "usr",
    "usr/bin",
    "usr/bin/zeditor",
    "usr/lib",
    "usr/lib/zed",
    "usr/lib/zed/zed-editor",
    "usr/share",
    "usr/share/applications",
    "usr/share/applications/dev.zed.Zed.desktop",
    "usr/share/bash-completion",
    "usr/share/bash-completion/completions",
    "usr/share/bash-completion/completions/zeditor",
    "usr/share/fish",
    "usr/share/fish/vendor_completions.d",
    "usr/share/fish/vendor_completions.d/zeditor.fish",
    "usr/share/icons",
    "usr/share/icons/hicolor",
    "usr/share/icons/hicolor/256x256",
    "usr/share/icons/hicolor/256x256/apps",
    "usr/share/icons/hicolor/256x256/apps/zed.png",
    "usr/share/metainfo",
    "usr/share/metainfo/dev.zed.Zed.metainfo.xml",
    "usr/share/zsh",
    "usr/share/zsh/site-functions",
    "usr/share/zsh/site-functions/_zeditor",
}


def build_bundle(directory: Path) -> Path:
    path = directory / "bundle.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        for name, payload in BUNDLE_MEMBERS.items():
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            info.mode = 0o644
            info.mtime = 1_700_000_000
            archive.addfile(info, io.BytesIO(payload))
    return path


class StagedTreeTest(unittest.TestCase):
    def test_staged_tree_matches_the_official_arch_layout(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            bundle = build_bundle(directory)
            output = directory / "out-pkgdir.tar.gz"
            build_arch_from_tarball(
                bundle,
                output,
                arch="x86_64",
                completions={
                    shell: f"# {shell} completions\n" for shell in COMPLETION_TARGETS
                },
                metainfo=render_metainfo(),
            )
            with tarfile.open(output, "r:gz") as archive:
                names = {member.name for member in archive.getmembers()}
        self.assertEqual(names, EXPECTED_TREE)

    def test_shell_completions_are_generated_for_all_three_shells(self) -> None:
        # The upstream bundle carries no completions; they exist only because
        # staging runs the CLI and captures them. Losing them here would be
        # invisible to a package that still installs.
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            bundle = build_bundle(directory)
            output = directory / "out-pkgdir.tar.gz"
            build_arch_from_tarball(
                bundle,
                output,
                arch="x86_64",
                completions={
                    shell: f"# {shell} completions\n" for shell in COMPLETION_TARGETS
                },
                metainfo=render_metainfo(),
            )
            with tarfile.open(output, "r:gz") as archive:
                for shell, target in COMPLETION_TARGETS.items():
                    payload = archive.extractfile(target).read().decode()
                    self.assertIn(shell, payload, f"{shell} completion content missing")
                    self.assertIn("completions", payload)

    def test_desktop_entry_execs_the_installed_binary_name(self) -> None:
        # clap derives completion function names from argv[0], and the desktop
        # entry has to launch the same name the package installs, or the menu
        # entry and the completions disagree about what the command is called.
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            bundle = build_bundle(directory)
            output = directory / "out-pkgdir.tar.gz"
            build_arch_from_tarball(
                bundle,
                output,
                arch="x86_64",
                completions={
                    shell: f"# {shell} completions\n" for shell in COMPLETION_TARGETS
                },
                metainfo=render_metainfo(),
            )
            with tarfile.open(output, "r:gz") as archive:
                desktop = archive.extractfile(
                    "usr/share/applications/dev.zed.Zed.desktop"
                ).read().decode()
        self.assertIn("Exec=zeditor ", desktop)
        self.assertNotIn("Exec=zed ", desktop)

    def test_bundled_libraries_are_dropped(self) -> None:
        # An Arch package links against the distribution's libraries; shipping
        # the bundle's own copies would shadow system updates.
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            bundle = build_bundle(directory)
            output = directory / "out-pkgdir.tar.gz"
            build_arch_from_tarball(
                bundle,
                output,
                arch="x86_64",
                completions={
                    shell: f"# {shell} completions\n" for shell in COMPLETION_TARGETS
                },
                metainfo=render_metainfo(),
            )
            with tarfile.open(output, "r:gz") as archive:
                names = {member.name for member in archive.getmembers()}
        self.assertFalse(any("/lib/" in name and name.endswith(".so") for name in names))
        self.assertNotIn("usr/lib/libfoo.so", names)


if __name__ == "__main__":
    unittest.main()
