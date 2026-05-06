import json
import tarfile
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

from moodle_mdx.compare import _activity_xml_fingerprint
from moodle_mdx.extract import extract_mdx_from_mbz
from moodle_mdx.mbz import build_mbz_from_mdx
from moodle_mdx.parser import parse_mdx
from moodle_mdx.validate import validate_mdx_file
from moodle_mdx.validate import validate_mdx_source


ROOT = Path(__file__).resolve().parents[1]
MINIMAL_MDX = ROOT / "examples" / "minimal" / "kurs.mdx"
REFERENCE_MBZ = Path("/Users/tlieber/Downloads/sicherung-moodle2-course-866-generated_test-20260506-1546-nu.mbz")
QUESTIONNAIRE_REFERENCE_MBZ = Path("/Users/tlieber/Downloads/sicherung-moodle2-course-867-generated_test2-20260506-1644-nu.mbz")


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

    def test_subsection_and_new_activity_types_build_standalone_mbz(self) -> None:
        source = """---
course:
  title: "Neue Typen"
  shortname: "NEU"
  format: "tiles"
backup:
  moodle_release: "4.5.10 (Build: 20260216)"
---

# Einstieg {index=0 moodle_title="Einstieg"}
summary: <p>Start</p>

:::label{title="Text"}
<p>## bleibt Inhalt im Label.</p>
:::

## Neuer Unterabschnitt

:::choice{title="Abstimmung" allowmultiple=true limitanswers=true timeopen=1778074560 timeclose=1778852160}
<p>Beschreibung</p>

- O1 {maxanswers=1}
- O2 {maxanswers=2}
:::

:::questionnaire{title="Befragung" opendate=1778074800 closedate=1778247600}
<p>Beschreibung</p>
:::

:::board{title="Board" background_color="bdb7ff" sortby=3}
<p>Beschreibung</p>

- Überschrift1
  - Beispielkarte links {heading="Start"}
- Überschrift2
- Überschrift3
:::
"""
        self.assertEqual(validate_mdx_source(source, base_dir=ROOT), [])
        model = parse_mdx(source)
        self.assertEqual([section.title for section in model.sections], ["Einstieg", "Neuer Unterabschnitt"])
        self.assertEqual([item.type for item in model.sections[0].items], ["label", "subsection", "choice", "questionnaire", "board"])
        self.assertEqual(model.sections[1].items, [])

        with tempfile.TemporaryDirectory() as tempdir:
            tmp_path = Path(tempdir)
            mdx_path = tmp_path / "kurs.mdx"
            output_mbz = tmp_path / "new-types.mbz"
            mdx_path.write_text(source, encoding="utf-8")

            build_mbz_from_mdx(mdx_path, output_mbz)

            with tarfile.open(output_mbz, "r:gz") as archive:
                names = set(archive.getnames())
                self.assertIn("activities/subsection_3001/subsection.xml", names)
                self.assertIn("activities/choice_3002/choice.xml", names)
                self.assertIn("activities/questionnaire_3003/questionnaire.xml", names)
                self.assertIn("activities/board_3004/board.xml", names)

                backup = ET.fromstring(archive.extractfile("moodle_backup.xml").read())  # type: ignore[union-attr]
                parent_section = ET.fromstring(archive.extractfile("sections/section_2000/section.xml").read())  # type: ignore[union-attr]
                child_section = ET.fromstring(archive.extractfile("sections/section_2001/section.xml").read())  # type: ignore[union-attr]
                choice = ET.fromstring(archive.extractfile("activities/choice_3002/choice.xml").read())  # type: ignore[union-attr]
                board = ET.fromstring(archive.extractfile("activities/board_3004/board.xml").read())  # type: ignore[union-attr]

            self.assertEqual(parent_section.findtext("sequence"), "3000,3001,3002,3003,3004")
            self.assertEqual(child_section.findtext("component"), "mod_subsection")
            self.assertEqual(child_section.findtext("itemid"), "4001")
            backup_sections = backup.findall("information/contents/sections/section")
            self.assertEqual(backup_sections[1].findtext("parentcmid"), "3001")
            self.assertEqual(backup_sections[1].findtext("modname"), "subsection")
            self.assertEqual(
                [(option.findtext("text"), option.findtext("maxanswers")) for option in choice.findall("choice/options/option")],
                [("O1", "1"), ("O2", "2")],
            )
            self.assertEqual(
                [column.findtext("name") for column in board.findall("board/columns/column")],
                ["Überschrift1", "Überschrift2", "Überschrift3"],
            )
            note = board.find("board/columns/column/notes/note")
            self.assertIsNotNone(note)
            self.assertEqual(note.findtext("heading"), "Start")  # type: ignore[union-attr]
            self.assertEqual(note.findtext("content"), "Beispielkarte links")  # type: ignore[union-attr]
            self.assertEqual(note.findtext("type"), "0")  # type: ignore[union-attr]
            settings = {
                setting.findtext("name"): setting.findtext("value")
                for setting in backup.findall("information/settings/setting")
            }
            self.assertEqual(settings["board_3004_userinfo"], "1")

    def test_reference_backup_fingerprints_new_activity_types(self) -> None:
        self.assertTrue(REFERENCE_MBZ.exists())

        fingerprint = _activity_xml_fingerprint(REFERENCE_MBZ)

        self.assertEqual(
            fingerprint["activities/choice_15224/choice.xml"][0:6],
            ("Abstimmung", "<p>Beschreibung</p>", "1", "0", "0", "0"),
        )
        self.assertEqual(
            fingerprint["activities/choice_15224/choice.xml"][-1],
            (("O1", "1"), ("O2", "2"), ("O3", "3"), ("O4", "4"), ("O5", "5")),
        )
        self.assertEqual(
            fingerprint["activities/questionnaire_15225/questionnaire.xml"][0:5],
            ("Befragung", "<p>Beschreibung</p>", "1", "1", "fullname"),
        )
        self.assertEqual(
            fingerprint["activities/board_15226/board.xml"][0:5],
            ("Board", "<p>Beschreibung</p>", "1", "bdb7ff", "0"),
        )
        self.assertEqual(
            fingerprint["activities/board_15226/board.xml"][-1],
            (("Überschrift1", "1", ()), ("Überschrift2", "2", ()), ("Überschrift3", "3", ())),
        )

    def test_questionnaire_reference_backup_fingerprints_all_question_types(self) -> None:
        self.assertTrue(QUESTIONNAIRE_REFERENCE_MBZ.exists())

        fingerprint = _activity_xml_fingerprint(QUESTIONNAIRE_REFERENCE_MBZ)
        questions = fingerprint["activities/questionnaire_15248/questionnaire.xml"][-1]

        self.assertEqual(
            [(question[1], question[3], question[5], question[7]) for question in questions],
            [
                ("Beschriftung: Name der Frage", "100", "0", "1"),
                ("", "99", "0", "2"),
                ("skala 1-x (hier 7", "8", "7", "3"),
                ("Name Checkboxen", "5", "0", "4"),
                ("", "99", "0", "5"),
                ("Name Datum", "9", "0", "6"),
                ("Name Dropdownfeld", "6", "0", "8"),
                ("", "99", "0", "7"),
                ("Name ja/nein", "1", "0", "9"),
                ("Name radio", "4", "1", "10"),
                ("Name Schieberegler", "11", "0", "11"),
                ("Name Texteingabe", "3", "20", "12"),
                ("Name des Textfeld", "2", "20", "13"),
            ],
        )
        self.assertEqual(questions[2][-1], (("mögliche Antworten", ""),))
        self.assertEqual(questions[6][-1], (("Wie radio", ""), ("antworten in zeilen", "")))
        self.assertIn('"minrange":"-3"', questions[10][11])
        self.assertEqual(
            questions[5][-2],
            (("4", "2", "1", "5", "3", "and"), ("4", "2", "1", "5", "3", "or")),
        )

    def test_questionnaire_reference_backup_extracts_all_question_types(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            output_path = Path(tempdir) / "extracted.mdx"

            extract_mdx_from_mbz(QUESTIONNAIRE_REFERENCE_MBZ, output_path)

            extracted = output_path.read_text(encoding="utf-8")

        self.assertIn('::::questionnaire{id="questionnaire_15248"', extracted)
        self.assertIn('survey_info="<p dir=\\"ltr\\" style=\\"text-align: left;\\">Beschreibung/Zusatzinfos</p>"', extracted)
        self.assertIn(':::q{type="sectiontext" name="Beschriftung: Name der Frage"', extracted)
        self.assertIn(':::q{type="pagebreak" name=""', extracted)
        self.assertIn(':::q{type="rate" name="skala 1-x (hier 7"', extracted)
        self.assertIn(':::q{type="checkbox" name="Name Checkboxen"', extracted)
        self.assertIn(':::q{type="date" name="Name Datum"', extracted)
        self.assertIn('depends_on="q4:c2,q4:c2"', extracted)
        self.assertIn('depends_join="and,or"', extracted)
        self.assertIn(':::q{type="dropdown" name="Name Dropdownfeld"', extracted)
        self.assertIn(':::q{type="yesno" name="Name ja/nein"', extracted)
        self.assertIn(':::q{type="radio" name="Name radio"', extracted)
        self.assertIn(':::q{type="slider" name="Name Schieberegler"', extracted)
        self.assertIn("minrange=-3 maxrange=3 startingvalue=0 stepvalue=1", extracted)
        self.assertIn('leftlabel="linke Beschriftung"', extracted)
        self.assertIn(':::q{type="text" name="Name Texteingabe"', extracted)
        self.assertIn(':::q{type="textarea" name="Name des Textfeld"', extracted)

    def test_questionnaire_questions_build_standalone_mbz(self) -> None:
        source = """---
course:
  title: "Questionnaire"
  shortname: "QUEST"
  format: "topics"
backup:
  moodle_release: "4.5.10 (Build: 20260216)"
---

# Einstieg

::::questionnaire{title="Befragung" opendate=1778074800 closedate=1778247600 survey_info="<p>Beschreibung/Zusatzinfos</p>" thank_head="Überschrift" thank_body="<p>Texterläuterung</p>" thanks_page="weiterleitungs url"}
<p>Beschreibung</p>

:::q{type="sectiontext" name="Beschriftung: Name der Frage"}
<h3>Blub blub</h3>
:::

:::q{type="pagebreak"}
:::

:::q{type="rate" name="skala 1-x" required=true length=7 extradata="[]"}
<p>Dies ist der Fragetext</p>

- mögliche Antworten
:::

:::q{id="checkboxen" type="checkbox" name="Name Checkboxen" precise=1}
<p>Fragetext</p>

- mögliche Antworten {id="option_a"}
:::

:::q{type="date" name="Name Datum" required=true depends_on="checkboxen:option_a"}
<p>Fragetext</p>
:::

:::q{type="dropdown" name="Name Dropdownfeld" required=true}
<p>Fragetext</p>

- Wie radio
- antworten in zeilen
:::

:::q{type="yesno" name="Name ja/nein" required=true}
<p>Fragetext</p>
:::

:::q{type="radio" name="Name radio" required=true length=1}
<p>Fragetext</p>

- wie dropdown
:::

:::q{type="slider" name="Name Schieberegler" minrange=-3 maxrange=3 startingvalue=0 stepvalue=1 leftlabel="linke Beschriftung" rightlabel="rechte Beschriftung" centerlabel="zentrale Beschriftung"}
<p>Fragetext</p>
:::

:::q{type="text" name="Name Texteingabe" required=true length=20}
<p>Fragtext</p>
:::

:::q{type="textarea" name="Name des Textfeld" required=true length=20 precise=25}
<p>Fragetext</p>
:::
::::
"""
        self.assertEqual(validate_mdx_source(source, base_dir=ROOT), [])
        model = parse_mdx(source)
        questionnaire = model.sections[0].items[0]
        self.assertEqual(questionnaire.type, "questionnaire")
        self.assertEqual(len(questionnaire.survey_questions), 11)

        with tempfile.TemporaryDirectory() as tempdir:
            tmp_path = Path(tempdir)
            mdx_path = tmp_path / "kurs.mdx"
            output_mbz = tmp_path / "questionnaire.mbz"
            mdx_path.write_text(source, encoding="utf-8")

            build_mbz_from_mdx(mdx_path, output_mbz)

            with tarfile.open(output_mbz, "r:gz") as archive:
                root = ET.fromstring(archive.extractfile("activities/questionnaire_3000/questionnaire.xml").read())  # type: ignore[union-attr]

        rendered = root.findall("questionnaire/surveys/survey/questions/question")
        self.assertEqual(
            [(question.findtext("type_id"), question.findtext("length"), question.findtext("precise")) for question in rendered],
            [
                ("100", "0", "0"),
                ("99", "0", "0"),
                ("8", "7", "0"),
                ("5", "0", "1"),
                ("9", "0", "0"),
                ("6", "0", "0"),
                ("1", "0", "0"),
                ("4", "1", "0"),
                ("11", "0", "0"),
                ("3", "20", "0"),
                ("2", "20", "25"),
            ],
        )
        self.assertEqual(
            [choice.findtext("content") for choice in rendered[5].findall("quest_choices/quest_choice")],
            ["Wie radio", "antworten in zeilen"],
        )
        dependencies = rendered[4].findall("quest_dependencies/quest_dependency")
        self.assertEqual(len(dependencies), 1)
        self.assertEqual(dependencies[0].findtext("dependquestionid"), rendered[3].get("id"))
        self.assertEqual(dependencies[0].findtext("dependchoiceid"), rendered[3].find("quest_choices/quest_choice").get("id"))  # type: ignore[union-attr]
        self.assertEqual(dependencies[0].findtext("dependlogic"), "1")
        self.assertEqual(dependencies[0].findtext("questionid"), rendered[4].get("id"))
        self.assertEqual(dependencies[0].findtext("dependandor"), "and")
        self.assertEqual(
            rendered[8].findtext("extradata"),
            '{"minrange":"-3","maxrange":"3","startingvalue":"0","stepvalue":"1","leftlabel":"linke Beschriftung","rightlabel":"rechte Beschriftung","centerlabel":"zentrale Beschriftung"}',
        )
        self.assertEqual(root.findtext("questionnaire/surveys/survey/thank_head"), "Überschrift")


if __name__ == "__main__":
    unittest.main()
