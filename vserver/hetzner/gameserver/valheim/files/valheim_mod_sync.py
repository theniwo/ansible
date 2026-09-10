#!/usr/bin/env python3
"""Synchronise pinned Thunderstore packages without touching manual plugins."""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
import urllib.error
import urllib.request
import zipfile

API_URL = "https://thunderstore.io/api/experimental/package/{namespace}/{name}/{version}/"
MARKER = ".ansible-valheim-mod.json"
IGNORED_PACKAGE = ("denikson", "BepInExPack_Valheim")
DEPENDENCY_RE = re.compile(r"^([^-]+)-(.+)-([0-9][0-9A-Za-z.+-]*)$")


class SyncError(RuntimeError):
    pass


def request_json(url):
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            return json.load(response)
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        raise SyncError(f"Thunderstore-Anfrage fehlgeschlagen ({url}): {exc}") from exc


def package_key(package):
    return package["namespace"], package["name"]


def validate_package(package, source):
    required = ("namespace", "name", "version")
    if not isinstance(package, dict) or any(not package.get(field) for field in required):
        raise SyncError(f"{source} muss namespace, name und eine exakte version enthalten")
    version = str(package["version"])
    for field in ("namespace", "name"):
        if not re.fullmatch(r"[A-Za-z0-9_.]+", str(package[field])):
            raise SyncError(f"Ungueltiges {field} in {source}: {package[field]!r}")
    if version.lower() == "latest" or not re.fullmatch(r"[0-9][0-9A-Za-z.+-]*", version):
        raise SyncError(f"Ungueltige, nicht exakt gepinnte Version in {source}: {version!r}")
    return {"namespace": str(package["namespace"]), "name": str(package["name"]), "version": version}


def parse_dependency(value):
    match = DEPENDENCY_RE.fullmatch(value)
    if not match:
        raise SyncError(f"Thunderstore lieferte eine ungueltige Dependency: {value!r}")
    return {"namespace": match.group(1), "name": match.group(2), "version": match.group(3)}


def resolve(requested):
    resolved = {}
    pending = list(requested)
    while pending:
        package = validate_package(pending.pop(), "Mod/Dependency")
        key = package_key(package)
        if key == IGNORED_PACKAGE:
            continue
        previous = resolved.get(key)
        if previous:
            if previous["version"] != package["version"]:
                raise SyncError(
                    f"Versionskonflikt fuer {key[0]}-{key[1]}: "
                    f"{previous['version']} und {package['version']}"
                )
            continue
        metadata = request_json(API_URL.format(**package))
        version = metadata.get("version", metadata)
        actual = str(version.get("version_number", package["version"]))
        if actual != package["version"]:
            raise SyncError(f"Thunderstore gab {actual} statt der gepinnten Version {package['version']} zurueck")
        package["download_url"] = version.get("download_url")
        package["dependencies"] = version.get("dependencies", [])
        if not package["download_url"]:
            raise SyncError(f"Keine Download-URL fuer {key[0]}-{key[1]}-{actual}")
        resolved[key] = package
        pending.extend(parse_dependency(dep) for dep in package["dependencies"])
    return resolved


def safe_members(archive):
    files = []
    for info in archive.infolist():
        path = PurePosixPath(info.filename)
        if path.is_absolute() or ".." in path.parts:
            raise SyncError(f"Unsicherer Pfad im Mod-Archiv: {info.filename}")
        if any(part.lower() == "patchers" for part in path.parts):
            raise SyncError(
                f"Paket enthaelt patchers/ ({info.filename}). Patcher werden nicht automatisch installiert."
            )
        if not info.is_dir():
            files.append((info, path))
    return files


def payload_path(path):
    lower = [part.lower() for part in path.parts]
    if "plugins" in lower:
        index = lower.index("plugins")
        remainder = path.parts[index + 1 :]
        return Path(*remainder) if remainder else None
    if len(path.parts) == 1 and path.suffix.lower() == ".dll":
        return Path(path.name)
    return None


def download_and_stage(package, staging):
    staging.mkdir()
    archive_path = staging / "package.zip"
    try:
        with urllib.request.urlopen(package["download_url"], timeout=60) as response, archive_path.open("wb") as output:
            shutil.copyfileobj(response, output)
    except (urllib.error.URLError, OSError) as exc:
        raise SyncError(f"Download von {package['namespace']}-{package['name']} fehlgeschlagen: {exc}") from exc

    destination = staging / "payload"
    destination.mkdir()
    hashes = {}
    try:
        with zipfile.ZipFile(archive_path) as archive:
            selected = [(info, payload_path(path)) for info, path in safe_members(archive)]
            selected = [(info, path) for info, path in selected if path is not None]
            if not selected:
                raise SyncError(f"{package['namespace']}-{package['name']} enthaelt keine Plugins")
            for info, relative in selected:
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
                hashes[relative.as_posix()] = hashlib.sha256(target.read_bytes()).hexdigest()
    except zipfile.BadZipFile as exc:
        raise SyncError(f"Ungueltiges ZIP fuer {package['namespace']}-{package['name']}") from exc

    marker = {
        "managed_by": "ansible-valheim-mod-sync",
        "namespace": package["namespace"],
        "name": package["name"],
        "version": package["version"],
        "files": hashes,
    }
    (destination / MARKER).write_text(json.dumps(marker, sort_keys=True, indent=2) + "\n")
    return destination


def current_marker(path):
    marker = path / MARKER
    try:
        data = json.loads(marker.read_text())
        if data.get("managed_by") != "ansible-valheim-mod-sync":
            return None
        for relative, expected in data.get("files", {}).items():
            if hashlib.sha256((path / relative).read_bytes()).hexdigest() != expected:
                return None
        return data
    except (OSError, json.JSONDecodeError, KeyError):
        return None


def sync(manifest_path, plugins_dir):
    manifest = json.loads(manifest_path.read_text())
    if not isinstance(manifest, dict) or not isinstance(manifest.get("mods", []), list):
        raise SyncError("mods.json muss ein Objekt mit einer mods-Liste enthalten")
    requested = [validate_package(item, "mods.json") for item in manifest.get("mods", [])]
    desired = resolve(requested)
    plugins_dir.mkdir(parents=True, exist_ok=True)
    managed = {path: current_marker(path) for path in plugins_dir.iterdir() if path.is_dir() and (path / MARKER).is_file()}
    desired_names = set()
    replacements = []

    with tempfile.TemporaryDirectory(prefix="valheim-mod-sync-") as temporary:
        root = Path(temporary)
        for _key, package in sorted(desired.items()):
            dirname = f"ansible-{package['namespace']}-{package['name']}"
            desired_names.add(dirname)
            target = plugins_dir / dirname
            marker = current_marker(target) if target.exists() else None
            if marker and marker.get("version") == package["version"]:
                continue
            if target.exists() and marker is None:
                raise SyncError(
                    f"Ziel {target} existiert, ist aber nicht eindeutig von Ansible verwaltet; "
                    "es wird zum Schutz manueller Mods nicht ersetzt"
                )
            staged = download_and_stage(package, root / dirname)
            replacements.append((target, staged))

        stale = [path for path, marker in managed.items() if marker and path.name not in desired_names]
        changed = bool(replacements or stale)
        for target, staged in replacements:
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(staged, target)
        for path in stale:
            shutil.rmtree(path)
    return changed, len(desired)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--plugins-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        changed, count = sync(args.manifest, args.plugins_dir)
    except (SyncError, OSError, json.JSONDecodeError) as exc:
        parser.exit(1, f"valheim_mod_sync: {exc}\n")
    print(json.dumps({"changed": changed, "resolved_mods": count}))


if __name__ == "__main__":
    main()
