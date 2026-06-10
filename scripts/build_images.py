"""Build one snapshot container per pinned repo (Chunk 4 deliverable #2).

For each `RepoPin`:
  1. Verify the snapshot hash is current.
  2. Render `Dockerfile.template` into a temp build context with `repo/`
     populated from `artifacts/repos/<short_id>/` (excluding byproducts).
  3. `docker build -t tokenbench/<short_id>:<dataset_version>` and record
     the resulting image digest into `artifacts/docker/digests.json`.

Usage:
    python scripts/build_images.py            # build all
    python scripts/build_images.py click      # build one

Daemon required. The digests file is what `needle_codebase.py` reads to
populate `RepoRef.docker_image` per Chunk 4 deliverable #2.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tokenbench.datasets.repo_pins import (  # noqa: E402
    REPO_PINS,
    SNAPSHOT_EXCLUDE_DIRS,
    hash_tree,
)

ARTIFACTS = ROOT / "artifacts" / "repos"
DOCKER_DIR = ROOT / "artifacts" / "docker"
DIGESTS_FILE = DOCKER_DIR / "digests.json"
DOCKERFILE = ROOT / "Dockerfile.template"
DATASET_VERSION = "1.0.0"  # mirrored from NeedleCodebaseDataset


def _copy_excluding_byproducts(src: Path, dst: Path) -> None:
    def ignore(_dir, names):
        return [n for n in names if n in SNAPSHOT_EXCLUDE_DIRS]

    shutil.copytree(src, dst, ignore=ignore)


def _docker_inspect_digest(image_ref: str) -> str:
    """Return the local Image ID (sha256:...) for a built image.

    We use `Id` (the content-addressed image ID) rather than `RepoDigests`,
    because RepoDigests are only populated after a push to a registry. The
    Id is stable across `docker build` invocations on identical context.
    """
    proc = subprocess.run(
        ["docker", "image", "inspect", image_ref, "--format", "{{.Id}}"],
        check=True,
        capture_output=True,
        text=True,
    )
    return proc.stdout.strip()


def build_one(pin) -> dict:
    src = ARTIFACTS / pin.short_id
    if not src.exists():
        raise FileNotFoundError(f"snapshot missing: {src}. Run scripts/snapshot_repos.py")
    actual = hash_tree(src)
    if actual != pin.snapshot_sha256:
        raise ValueError(
            f"{pin.short_id}: snapshot hash drift before build "
            f"(recorded={pin.snapshot_sha256[:12]} actual={actual[:12]})"
        )

    image_ref = f"tokenbench/{pin.short_id}:{DATASET_VERSION}"
    print(f"[build] {image_ref}  context-from={src}")

    with tempfile.TemporaryDirectory() as ctx_root:
        ctx = Path(ctx_root)
        shutil.copy2(DOCKERFILE, ctx / "Dockerfile")
        _copy_excluding_byproducts(src, ctx / "repo")

        subprocess.run(
            [
                "docker", "build",
                "-t", image_ref,
                "--build-arg", f"REPO_SHORT_ID={pin.short_id}",
                "--build-arg", f"REPO_COMMIT={pin.commit}",
                "--build-arg", f"SNAPSHOT_SHA256={pin.snapshot_sha256}",
                "--build-arg", f"DATASET_VERSION={DATASET_VERSION}",
                str(ctx),
            ],
            check=True,
        )

    digest = _docker_inspect_digest(image_ref)
    print(f"        digest={digest}")
    return {
        "short_id": pin.short_id,
        "image_ref": image_ref,
        "image_id": digest,
        "repo_commit": pin.commit,
        "snapshot_sha256": pin.snapshot_sha256,
        "dataset_version": DATASET_VERSION,
    }


def main(argv: list[str]) -> int:
    if len(argv) > 1:
        by_short = {p.short_id: p for p in REPO_PINS}
        if argv[1] not in by_short:
            print(f"unknown short_id: {argv[1]!r}", file=sys.stderr)
            return 2
        pins = [by_short[argv[1]]]
    else:
        pins = list(REPO_PINS)

    DOCKER_DIR.mkdir(parents=True, exist_ok=True)
    digests = {}
    if DIGESTS_FILE.exists():
        digests = {e["short_id"]: e for e in json.loads(DIGESTS_FILE.read_text())["images"]}

    for pin in pins:
        digests[pin.short_id] = build_one(pin)

    DIGESTS_FILE.write_text(
        json.dumps(
            {"dataset_version": DATASET_VERSION, "images": list(digests.values())},
            indent=2,
        )
        + "\n"
    )
    print(f"\n[ok] wrote {DIGESTS_FILE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
