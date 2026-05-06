# mdx2moodle

Dieses Projekt erstellt Moodle-Kurse aus gut lesbaren MDX-Dateien. Ziel ist,
Kursinhalte nicht direkt in Moodle zusammenzuklicken, sondern sie als Text zu
beschreiben, versionierbar zu halten und daraus ein restore-fähiges
Moodle-Backup (`.mbz`) zu bauen.

MDX bleibt dabei für Menschen gut lesbar und kann zugleich von LLMs gut erzeugt
und überarbeitet werden: Überschriften, Absätze, Listen und eingebettetes HTML
beschreiben die Inhalte, zusätzliche Directives beschreiben Moodle-Aktivitäten.
Aktuell kann der Builder daraus unter anderem Labels, Bücher, Tests, Aufgaben,
Foren, Ordner, GeoGebra-Aktivitäten, Abstimmungen, Befragungen, Boards und
Subsections erzeugen. Weitere Moodle-Aktivitäten werden nach und nach ergänzt.

Der normale Arbeitsfluss ist:

1. Kurs als MDX schreiben.
2. Lokale Assets wie PDFs oder GeoGebra-Dateien beilegen.
3. MDX validieren.
4. `.mbz` bauen.
5. `.mbz` in Moodle als Kurs wiederherstellen.

Ein vollständiges, templatefreies Beispiel liegt unter
`examples/minimal/kurs.mdx`.

## Unterstützte Inhalte

Der Standalone-Build erzeugt eine neue Moodle-Backup-Struktur mit synthetischen
IDs, Restore-Settings und den notwendigen Moodle-Sidecars. Aktuell unterstützt:

- Kurs-Metadaten und Tiles-Formatoptionen
- Sections und Labels
- Books mit verschachtelten Seiten
- Quizze mit `multichoice`-Fragen
- Assign, Forum, Folder und GeoGebra
- Subsections, Choice, Questionnaire und Board in der referenzgetreuen
  v1-Struktur aus Moodle 4.5.10
- Questionnaire-Fragen für Beschriftung, Seitenumbruch, Skala, Checkbox,
  Datum, Dropdown, Ja/Nein, Radio, Schieberegler, Texteingabe und Textfeld
- Questionnaire-Anzeige-Logik mit `depends_on="frage:antwort"`
- Board-Seedkarten als rohe Markdown-Inhalte, die vom Moodle-Board-Plugin
  gerendert werden
- lokale Asset-Dateien im Moodle-File-Pool

## Beispiel

```mdx
---
course:
  title: "Beispielkurs"
  shortname: "BEISPIEL"
  format: "tiles"
backup:
  moodle_release: "4.5.10 (Build: 20260216)"
---

# Einstieg
summary: <p>Ein kurzer Einstieg in den Kurs.</p>

:::label{title="Willkommen"}
<p>Willkommen im Kurs.</p>
:::

::::quiz{title="Kurzer Selbsttest"}
:::question{type="multichoice" name="Erste Frage" single=true}
Welche Aussage stimmt?

- [x] Dieser Kurs wurde aus MDX erzeugt.
- [ ] Dieser Kurs wurde manuell in Moodle geklickt.
:::
::::

:::board{title="Ideensammlung"}
<p>Beispielhafte Startkarten für die Lerngruppe.</p>

- Erste Spalte
  - Karte mit **Markdown** und *Hervorhebung* {heading="Start"}
- Zweite Spalte
:::

::::questionnaire{title="Rückmeldung" thank_head="Danke"}
<p>Kurze Rückmeldung zum Arbeitsstand.</p>

:::q{id="schule_spass" type="radio" name="Macht dir Schule Spaß?" required=true length=1}
<p>Macht dir Schule Spaß?</p>

- Ja {id="ja"}
- Nein {id="nein"}
:::

:::q{id="warum_nicht" type="textarea" name="Warum nicht?" length=40 precise=5 depends_on="schule_spass:nein"}
<p>Warum macht dir Schule im Moment keinen Spaß?</p>
:::
::::
```

Die vollständige Syntax ist in der Dokumentation beschrieben:

- [MDX-Syntax](docs/mdx-syntax.md)

## Befehle

Minimalbeispiel validieren:

```bash
PYTHONPATH=src python3 -m moodle_mdx.cli validate examples/minimal/kurs.mdx
```

Minimalbeispiel als Moodle-Backup bauen:

```bash
PYTHONPATH=src python3 -m moodle_mdx.cli build examples/minimal/kurs.mdx out/minimal.mbz --manifest out/minimal_manifest.json
```

MBZ-Struktur inspizieren:

```bash
PYTHONPATH=src python3 -m moodle_mdx.cli inspect-mbz out/minimal.mbz
```

MDX aus einer vorhandenen Sicherung extrahieren:

```bash
PYTHONPATH=src python3 -m moodle_mdx.cli extract-mdx kurs.mbz out/extracted/kurs.mdx
```

Zwei Sicherungen semantisch vergleichen:

```bash
PYTHONPATH=src python3 -m moodle_mdx.cli compare referenz.mbz out/minimal.mbz
```

Die erzeugte Datei `out/minimal.mbz` kann anschließend in Moodle über die
Wiederherstellen-Funktion als Kurs importiert werden.

## Tests

```bash
PYTHONPATH=src python3 -m unittest tests.test_standalone_public -v
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Die Tests prüfen unter anderem, dass das Minimalbeispiel validiert, eine
Standalone-MBZ erzeugt, die neuen Aktivitätstypen samt Questionnaire-Logik
rendert und Referenzsicherungen semantisch erkannt werden.
