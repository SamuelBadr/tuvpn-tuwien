#!/usr/bin/env python3
"""Build a self-contained, relocatable OpenConnect runtime for TUvpn.

The Homebrew installation is user-owned. Running it from a NOPASSWD root helper
would let any process running as that user replace executable code. This script
copies OpenConnect and every Homebrew dylib it links into one staging tree,
rewrites load commands to that tree, and ad-hoc signs the result. The staged
runtime is installed root-owned by install.sh.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
from typing import Dict, Iterable, List, Set, Tuple

ROOT = Path(__file__).resolve().parent
STAGE = ROOT / "build" / "tuwien-openconnect-9.21"
VPNC_SOURCE = ROOT / "src" / "vpnc-script"
INSTALL_ROOT = Path("/usr/local/libexec/tuwien-openconnect-9.21")
P11_CONFIG_DIR = Path("/usr/local/etc/tuvpn-p11")


def brew_executable() -> str:
    """Locate brew so the builder survives Homebrew version upgrades."""
    found = shutil.which("brew")
    if found:
        return found
    for candidate in ("/opt/homebrew/bin/brew", "/usr/local/bin/brew"):
        if Path(candidate).is_file():
            return candidate
    raise RuntimeError("Homebrew not found; install from https://brew.sh")


def brew_prefix(formula: str) -> Path:
    """Return a formula's opt-prefix (stable across version bumps)."""
    result = subprocess.run(
        [brew_executable(), "--prefix", formula],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return Path(result.stdout.strip())


# Discover the source binaries via `brew --prefix` instead of hardcoding the
# Cellar version, so a `brew upgrade` that bumps openconnect/p11-kit does not
# break the builder.
SOURCE = brew_prefix("openconnect") / "bin" / "openconnect"
TRUST_MODULE = brew_prefix("p11-kit") / "lib" / "pkcs11" / "p11-kit-trust.dylib"


def run(*args: str, capture: bool = False) -> str:
    result = subprocess.run(
        args,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )
    return result.stdout if capture else ""


def dependencies(path: Path) -> List[str]:
    output = run("/usr/bin/otool", "-L", str(path), capture=True)
    result: List[str] = []
    for line in output.splitlines()[1:]:
        match = re.match(r"\s*(\S+)\s+\(", line)
        if match:
            result.append(match.group(1))
    return result


def collect_runtime(starts: Iterable[Path]) -> Tuple[List[Path], Dict[str, Path]]:
    pending = [item.resolve() for item in starts]
    seen: Set[Path] = set()
    original_to_real: Dict[str, Path] = {}
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        for dependency in dependencies(current):
            if not dependency.startswith("/opt/homebrew/"):
                continue
            resolved = Path(dependency).resolve()
            if not resolved.is_file():
                raise RuntimeError(f"missing Homebrew dependency: {dependency}")
            original_to_real[dependency] = resolved
            pending.append(resolved)
    return sorted(seen), original_to_real


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prepare_directories() -> None:
    for directory in (
        STAGE,
        STAGE / "bin",
        STAGE / "lib",
        STAGE / "pkcs11",
        STAGE / "p11-config",
        STAGE / "scripts",
    ):
        directory.mkdir(parents=True, exist_ok=True)
        directory.chmod(0o755)


def replace_embedded_path(path: Path, old: str, new: str) -> None:
    """Replace a NUL-terminated compiled path without changing Mach-O size."""
    old_bytes = old.encode() + b"\0"
    new_raw = new.encode()
    if len(new_raw) > len(old.encode()):
        raise RuntimeError(f"replacement path is too long: {new!r} for {old!r}")
    data = path.read_bytes()
    count = data.count(old_bytes)
    if count != 1:
        raise RuntimeError(f"expected one embedded path {old!r} in {path}, found {count}")
    replacement = new_raw + b"\0" * (len(old_bytes) - len(new_raw))
    path.write_bytes(data.replace(old_bytes, replacement))


def main() -> int:
    if not SOURCE.is_file() or not TRUST_MODULE.is_file() or not VPNC_SOURCE.is_file():
        print("Homebrew OpenConnect 9.21 or its vpnc-script is missing", file=sys.stderr)
        return 1

    prepare_directories()
    runtime_files, original_to_real = collect_runtime((SOURCE, TRUST_MODULE))

    basename_sources: Dict[str, Path] = {}
    for source in runtime_files:
        if source in (SOURCE.resolve(), TRUST_MODULE.resolve()):
            continue
        existing = basename_sources.get(source.name)
        if existing and existing != source and sha256(existing) != sha256(source):
            raise RuntimeError(f"dependency basename collision: {existing} and {source}")
        basename_sources[source.name] = source

    binary_destination = STAGE / "bin" / "openconnect"
    shutil.copy2(SOURCE.resolve(), binary_destination)
    binary_destination.chmod(0o755)

    trust_destination = STAGE / "pkcs11" / "p11-kit-trust.dylib"
    shutil.copy2(TRUST_MODULE.resolve(), trust_destination)
    trust_destination.chmod(0o644)

    copied: Dict[Path, Path] = {
        SOURCE.resolve(): binary_destination,
        TRUST_MODULE.resolve(): trust_destination,
    }
    for name, source in basename_sources.items():
        destination = STAGE / "lib" / name
        shutil.copy2(source, destination)
        destination.chmod(0o644)
        copied[source] = destination

    # p11-kit otherwise discovers and loads a trust module from the user-owned
    # Homebrew tree. Redirect its compiled configuration/module paths to
    # root-owned locations and make the trust module use macOS's CA bundle.
    p11_destination = next(
        destination for source, destination in copied.items() if source.name == "libp11-kit.0.dylib"
    )
    # Derive the p11-kit Cellar prefix from the resolved module path so a version
    # bump (e.g. 0.26.4 -> 0.26.5) does not break the embedded-path rewrites.
    p11_kit_cellar = str(TRUST_MODULE.resolve().parents[2])
    for old, new in (
        ("/opt/homebrew/etc/pkcs11/modules", str(P11_CONFIG_DIR)),
        ("/opt/homebrew/etc/modules", str(P11_CONFIG_DIR)),
        ("/opt/homebrew/etc/pkcs11.conf", "/usr/local/etc/tuvpn.conf"),
        (f"{p11_kit_cellar}/lib/pkcs11", "/usr/local/lib/tuvpn-p11"),
    ):
        replace_embedded_path(p11_destination, old, new)

    for old, new in (
        (f"{p11_kit_cellar}/etc", "/usr/local/etc/tuvpn-p11"),
        (f"{p11_kit_cellar}/share", "/usr/local/share/tuvpn-p11"),
        ("/opt/homebrew/etc/ca-certificates/cert.pem", "/etc/ssl/cert.pem"),
    ):
        replace_embedded_path(trust_destination, old, new)

    # Rewrite every Homebrew load command. System frameworks and /usr/lib stay
    # untouched and remain protected by macOS.
    for source, destination in copied.items():
        if source == SOURCE.resolve():
            replacement_prefix = "@executable_path/../lib"
        elif source == TRUST_MODULE.resolve():
            replacement_prefix = "@loader_path/../lib"
        else:
            replacement_prefix = "@loader_path"
        for original in dependencies(source):
            if not original.startswith("/opt/homebrew/"):
                continue
            resolved = Path(original).resolve()
            target = copied.get(resolved)
            if target is None:
                raise RuntimeError(f"unmapped dependency {original} from {source}")
            run(
                "/usr/bin/install_name_tool",
                "-change",
                original,
                f"{replacement_prefix}/{target.name}",
                str(destination),
            )
        if source != SOURCE.resolve():
            run("/usr/bin/install_name_tool", "-id", f"@rpath/{destination.name}", str(destination))
        run("/usr/bin/codesign", "--force", "--sign", "-", str(destination))

    vpnc_destination = STAGE / "scripts" / "vpnc-script"
    shutil.copy2(VPNC_SOURCE, vpnc_destination)
    vpnc_destination.chmod(0o755)

    module_config = STAGE / "p11-config" / "p11-kit-trust.module"
    module_config.write_text(
        f"module: {INSTALL_ROOT}/pkcs11/p11-kit-trust.dylib\n"
        "priority: 1\n"
        "trust-policy: yes\n"
        "disable-in: p11-kit-proxy\n"
    )
    module_config.chmod(0o644)

    # Ensure the vendored binaries no longer load executable code from the
    # user-owned Homebrew prefix.
    for destination in copied.values():
        leaked = [item for item in dependencies(destination) if item.startswith("/opt/homebrew/")]
        if leaked:
            raise RuntimeError(f"unrelocated dependencies in {destination}: {leaked}")

    version = run(str(binary_destination), "--version", capture=True).splitlines()[0]
    manifest_path = STAGE / "manifest.json"
    manifest = {
        "openconnect": version,
        "source": str(SOURCE),
        "vpnc_source": str(VPNC_SOURCE),
        "files": {
            str(path.relative_to(STAGE)): sha256(path)
            for path in sorted(
                p for p in STAGE.rglob("*") if p.is_file() and p != manifest_path
            )
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    manifest_path.chmod(0o644)

    print(STAGE)
    print(version)
    print(f"vendored files: {len(manifest['files'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
