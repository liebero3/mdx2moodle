import json
import tarfile
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

from moodle_mdx.mbz import build_mbz_from_mdx
from moodle_mdx.validate import validate_mdx_file


ROOT = Path(__file__).resolve().parents[1]
MINIMAL_MDX = ROOT / "examples" / "minimal" / "kurs.mdx"


class StandalonePublicTests(unittest.TestCase):
    def test_minimal_mdx_without_template_validates(self) -> None:
        self.assertEqual(validate_mdx_file(MINIMAL_MDX), [])

    def test_minimal_mdx_without_template_builds_standalone_mbz(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            tmp_path = Path(tempdir)
            output_mbz = tmp_path / "minimal.mbz"
            manifest_path = tmp_path / "minimal_manifest.json"

            build_mbz_from_mdx(MINIMAL_MDX, output_mbz, manifest_path=manifest_path)

            self.assertTrue(output_mbz.exists())
            self.assertTrue(tarfile.is_tarfile(output_mbz))
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["build"]["mode"], "standalone")
            self.assertNotIn("template", manifest["backup"])

            with tarfile.open(output_mbz, "r:gz") as archive:
                names = set(archive.getnames())
                self.assertIn("moodle_backup.xml", names)
                self.assertIn("course/course.xml", names)
                self.assertIn("activities/folder_3005/folder.xml", names)
                self.assertIn("activities/geogebra_3006/geogebra.xml", names)
                self.assertIn("questions.xml", names)
                self.assertIn("files.xml", names)

                course = ET.fromstring(archive.extractfile("course/course.xml").read())  # type: ignore[union-attr]
                geogebra = ET.fromstring(archive.extractfile("activities/geogebra_3006/geogebra.xml").read())  # type: ignore[union-attr]
                files = ET.fromstring(archive.extractfile("files.xml").read())  # type: ignore[union-attr]

            self.assertEqual(course.findtext("fullname"), "Minimaler Sprint-6-Kurs")
            self.assertEqual(geogebra.findtext("geogebra/url"), "geogebra.ggb")
            self.assertEqual(
                [file.findtext("mimetype") for file in files.findall("file") if file.findtext("filename") == "geogebra.ggb"],
                ["application/zip"],
            )
            self.assertTrue(any(file.findtext("filename") == "material.pdf" for file in files.findall("file")))


if __name__ == "__main__":
    unittest.main()
