import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest


SCRIPT = Path(__file__).parents[1] / "files" / "valheim_mkworld.py"
SPEC = importlib.util.spec_from_file_location("valheim_mkworld", SCRIPT)
mkworld = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mkworld)


def read_string(data, offset):
    length = 0
    shift = 0
    while True:
        byte = data[offset]
        offset += 1
        length |= (byte & 0x7F) << shift
        if not byte & 0x80:
            break
        shift += 7
    value = data[offset : offset + length].decode("utf-8")
    return value, offset + length


class WorldCreationTests(unittest.TestCase):
    def test_stable_hash_uses_signed_32_bit_valheim_algorithm(self):
        self.assertEqual(mkworld.stable_hash("Meadows42"), -801179158)
        self.assertEqual(mkworld.stable_hash("a"), 372029373)

    def test_world_data_contains_expected_fwl_fields(self):
        data = mkworld.world_data("Midgard", "Meadows42", uid=123456789)
        version = struct.unpack_from("<i", data)[0]
        name, offset = read_string(data, 4)
        seed, offset = read_string(data, offset)
        seed_hash, uid, generator_version, needs_db = struct.unpack_from("<iqi?", data, offset)

        self.assertEqual(version, mkworld.WORLD_METADATA_VERSION)
        self.assertEqual(name, "Midgard")
        self.assertEqual(seed, "Meadows42")
        self.assertEqual(seed_hash, mkworld.stable_hash(seed))
        self.assertEqual(uid, 123456789)
        self.assertEqual(generator_version, mkworld.WORLD_GENERATOR_VERSION)
        self.assertTrue(needs_db)
        self.assertEqual(offset + struct.calcsize("<iqi?"), len(data))

    def test_seed_must_be_one_to_ten_ascii_alphanumeric_characters(self):
        for seed in ("", "12345678901", "seed-name", "Méadows", "seed space"):
            with self.subTest(seed=seed), self.assertRaises(mkworld.WorldError):
                mkworld.world_data("Midgard", seed)

    def test_existing_world_metadata_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "Midgard.fwl"
            output.write_bytes(b"existing world")
            with self.assertRaisesRegex(mkworld.WorldError, "refusing to overwrite"):
                mkworld.create_world("Midgard", "Meadows42", output)
            self.assertEqual(output.read_bytes(), b"existing world")


if __name__ == "__main__":
    unittest.main()
