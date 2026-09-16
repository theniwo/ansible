#!/usr/bin/env python3
"""Create initial Valheim world metadata containing a custom seed."""

import argparse
import re
import struct
import time
from pathlib import Path


SEED_RE = re.compile(r"[A-Za-z0-9]{1,10}", re.ASCII)
# This established metadata format contains all fields needed for a new world
# and is upgraded by newer Valheim server releases when first loaded.
WORLD_METADATA_VERSION = 29
WORLD_GENERATOR_VERSION = 1
DOTNET_EPOCH_TICKS = 621_355_968_000_000_000


class WorldError(ValueError):
    """Raised when world metadata cannot safely be created."""


def int32(value):
    """Apply the signed 32-bit overflow semantics used by C#."""
    value &= 0xFFFFFFFF
    return value if value < 0x80000000 else value - 0x100000000


def stable_hash(value):
    """Return Valheim/Unity's deterministic string hash as a signed int32."""
    hash1 = 5381
    hash2 = 5381
    for index in range(0, len(value), 2):
        hash1 = int32(((hash1 << 5) + hash1) ^ ord(value[index]))
        if index == len(value) - 1:
            break
        hash2 = int32(((hash2 << 5) + hash2) ^ ord(value[index + 1]))
    return int32(hash1 + int32(hash2 * 1_566_083_941))


def encoded_string(value):
    """Encode a string as written by System.IO.BinaryWriter."""
    payload = value.encode("utf-8")
    length = len(payload)
    prefix = bytearray()
    while length >= 0x80:
        prefix.append((length & 0x7F) | 0x80)
        length >>= 7
    prefix.append(length)
    return bytes(prefix) + payload


def world_data(name, seed, uid=None):
    if not name or any(ord(character) < 32 for character in name):
        raise WorldError("WORLD_NAME must not be empty or contain control characters")
    if not SEED_RE.fullmatch(seed):
        raise WorldError("SEED must contain 1 to 10 ASCII letters or digits")
    if uid is None:
        uid = DOTNET_EPOCH_TICKS + time.time_ns() // 100
    if not 0 <= uid <= 0x7FFFFFFFFFFFFFFF:
        raise WorldError("world UID is outside the signed 64-bit range")

    return b"".join(
        (
            struct.pack("<i", WORLD_METADATA_VERSION),
            encoded_string(name),
            encoded_string(seed),
            struct.pack("<i", stable_hash(seed)),
            struct.pack("<q", uid),
            struct.pack("<i", WORLD_GENERATOR_VERSION),
            struct.pack("<?", True),
        )
    )


def create_world(name, seed, output):
    data = world_data(name, seed)
    try:
        with output.open("xb") as world_file:
            world_file.write(data)
    except FileExistsError as exc:
        raise WorldError(f"refusing to overwrite existing world metadata: {output}") from exc


def main():
    parser = argparse.ArgumentParser(
        prog="valheim-mkworld",
        description="Create initial Valheim .fwl metadata with a custom seed.",
    )
    parser.add_argument("world_name", metavar="WORLD_NAME")
    parser.add_argument("seed", metavar="SEED")
    parser.add_argument("output_file", metavar="OUTPUT_FILE", type=Path)
    args = parser.parse_args()
    try:
        create_world(args.world_name, args.seed, args.output_file)
    except (OSError, WorldError) as exc:
        parser.exit(1, f"valheim-mkworld: {exc}\n")


if __name__ == "__main__":
    main()
