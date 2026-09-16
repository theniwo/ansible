import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile


SCRIPT = Path(__file__).parents[1] / "files" / "valheim_mod_sync.py"
SPEC = importlib.util.spec_from_file_location("valheim_mod_sync", SCRIPT)
mod_sync = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod_sync)


def package_metadata(namespace, name, version, dependencies=None):
    return {
        "namespace": namespace,
        "name": name,
        "version_number": version,
        "download_url": f"https://example.invalid/{namespace}-{name}-{version}.zip",
        "dependencies": dependencies or [],
    }


def plugin_archive(filename="Example.dll", contents=b"plugin"):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(f"BepInEx/plugins/{filename}", contents)
    return output.getvalue()


class ModSyncTests(unittest.TestCase):
    def test_validate_package_requires_three_part_numeric_version(self):
        for version in ("latest", "1", "1.2", "1.2.3-beta"):
            with self.subTest(version=version), self.assertRaises(mod_sync.SyncError):
                mod_sync.validate_package(
                    {"namespace": "Author", "name": "Mod", "version": version},
                    "test",
                )

    def test_resolve_dependencies_recursively_and_skips_image_bepinex(self):
        metadata = {
            ("Author", "Root", "1.0.0"): package_metadata(
                "Author",
                "Root",
                "1.0.0",
                ["Dependency-Leaf-2.0.0", "denikson-BepInExPack_Valheim-5.4.2202"],
            ),
            ("Dependency", "Leaf", "2.0.0"): package_metadata(
                "Dependency", "Leaf", "2.0.0"
            ),
        }

        def request(url):
            coordinates = tuple(url.rstrip("/").split("/")[-3:])
            return metadata[coordinates]

        with mock.patch.object(mod_sync, "request_json", side_effect=request):
            resolved = mod_sync.resolve(
                [{"namespace": "Author", "name": "Root", "version": "1.0.0"}]
            )

        self.assertEqual(set(resolved), {("Author", "Root"), ("Dependency", "Leaf")})

    def test_patchers_are_rejected(self):
        archive_data = io.BytesIO()
        with zipfile.ZipFile(archive_data, "w") as archive:
            archive.writestr("BepInEx/patchers/Unsafe.dll", b"patcher")
        with zipfile.ZipFile(io.BytesIO(archive_data.getvalue())) as archive:
            with self.assertRaisesRegex(mod_sync.SyncError, "Patcher werden nicht automatisch installiert"):
                mod_sync.safe_members(archive)

    def test_sync_is_idempotent_removes_only_marked_stale_mods(self):
        root_package = package_metadata("Author", "Root", "1.0.0")
        archive = plugin_archive()

        def urlopen(_request, timeout):
            del timeout
            return io.BytesIO(archive)

        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            manifest = base / "mods.json"
            manifest.write_text(
                json.dumps({"mods": [{"namespace": "Author", "name": "Root", "version": "1.0.0"}]})
            )
            plugins = base / "plugins"
            plugins.mkdir()
            manual = plugins / "ManuallyInstalled"
            manual.mkdir()
            (manual / "Manual.dll").write_bytes(b"manual")
            stale = plugins / "ansible-Old-Stale"
            stale.mkdir()
            (stale / mod_sync.MARKER).write_text(
                json.dumps({"managed_by": "ansible-valheim-mod-sync", "files": {}})
            )

            with mock.patch.object(mod_sync, "request_json", return_value=root_package), mock.patch.object(
                mod_sync.urllib.request, "urlopen", side_effect=urlopen
            ):
                self.assertEqual(mod_sync.sync(manifest, plugins), (True, 1))
                self.assertEqual(mod_sync.sync(manifest, plugins), (False, 1))

            self.assertTrue((manual / "Manual.dll").is_file())
            self.assertFalse(stale.exists())
            self.assertTrue((plugins / "ansible-Author-Root" / "Example.dll").is_file())


if __name__ == "__main__":
    unittest.main()
