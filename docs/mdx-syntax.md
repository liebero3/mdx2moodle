# MDX-Syntax

Diese Datei beschreibt den aktuell implementierten MDX-Dialekt von
`mdx2moodle`. Dokumentiert ist nur Syntax, die der Parser heute versteht.
Weitere Moodle-Aktivitäten werden nach und nach ergänzt.

Der Builder erzeugt aus einer MDX-Datei eine neue Moodle-Backup-Struktur mit
synthetischen IDs, Restore-Settings und den notwendigen Sidecars. Relative
Asset-Pfade werden relativ zur MDX-Datei aufgelöst.

## Pipeline

```text
kurs.mdx
  -> Parser
  -> CourseModel
  -> Manifest
  -> MBZ-Builder
  -> .mbz
```

```bash
PYTHONPATH=src python3 -m moodle_mdx.cli validate examples/minimal/kurs.mdx
PYTHONPATH=src python3 -m moodle_mdx.cli build examples/minimal/kurs.mdx out/minimal.mbz --manifest out/minimal_manifest.json
```

## Frontmatter

Jede MDX-Datei beginnt mit einfachem YAML-Frontmatter. Der aktuelle Parser
unterstützt flache Schlüssel und eine Einrückungsebene.

```mdx
---
course:
  title: "Beispielkurs"
  shortname: "BEISPIEL"
  format: "tiles"
  startdate: 1777932000
  enddate: 0
  visible: true
  enablecompletion: true
tiles:
  hiddensections: 1
  coursedisplay: 1
  defaulttileicon: "pie-chart"
  basecolour: "#1670CC"
backup:
  moodle_release: "4.5.10 (Build: 20260216)"
---
```

`course.title`, `course.shortname` und `course.format` landen im Manifest und
in `course/course.xml`. Weitere `course`-Felder werden als Moodle-Settings
weitergereicht.

`tiles` beschreibt kursweite Formatoptionen für das Moodle-Tiles-Format.

Der Builder erzeugt deterministische IDs und Pfade: Course `1`,
Course-Context `1000`, Sections ab `2000`, Module ab `3000`,
Activity-Instanzen ab `4000`, Activity-Kontexte ab `5000`,
Question-Bank-IDs ab `6000` und File-IDs ab `7000`.

## Sections

Eine H1-Überschrift erzeugt einen Moodle-Kursabschnitt.

```mdx
# Einstieg {index=0 moodle_title="Einstieg"}
summary: <p>Ein kurzer Einstieg in den Kurs.</p>
```

Attribute:

- `index`: optionale Moodle-Abschnittsnummer. Wenn sie fehlt, zählt der Parser.
- `moodle_title`: optionaler Moodle-Anzeigetitel. Ohne Attribut wird der
  H1-Text verwendet.

Eine Section-Summary kann als `summary:`-Zeile oder als Directive geschrieben
werden.

```mdx
:::sectionSummary
<p>Mehrzeilige HTML-Zusammenfassung.</p>
:::
```

## Directives

Moodle-Aktivitäten werden als Directive-Blöcke geschrieben.

```mdx
:::label{title="Willkommen"}
<p>Willkommen im Kurs.</p>
:::
```

Gemeinsame Attribute:

- `title`: Aktivitätstitel.
- `visible`: optional; Default ist `true`.

Der öffnende und schließende Fence muss dieselbe Anzahl Doppelpunkte haben.
Für verschachtelte Blöcke wird außen ein längerer Fence verwendet.

## Label

```mdx
:::label{title="Willkommen"}
<section>
  <h3>Start</h3>
  <p>Kurzer Orientierungstext.</p>
</section>
:::
```

Der Body wird als HTML in `label/intro` geschrieben. `label/name` wird aus
`title` gerendert.

## Book

Books verwenden einen äußeren `::::book`-Block und darin verschachtelte
`:::page`-Blöcke.

```mdx
::::book{title="Lernbuch"}
:::page{title="Erste Seite"}
<p>Eine kurze Lernbuchseite.</p>
:::
::::
```

Book-Attribute:

- `title`: Titel der Book-Aktivität.

Page-Attribute:

- `title`: Kapiteltitel.
- `subchapter`: optional; `true` erzeugt ein Unterkapitel.

## Quiz

Quizze verwenden einen äußeren `::::quiz`-Block und darin `:::question`-Blöcke.
Aktuell unterstützt sind `multichoice`-Fragen.

```mdx
::::quiz{title="Kurzer Selbsttest"}
:::question{type="multichoice" name="Erste Frage" single=true shuffleanswers=false}
Welche Aussage stimmt?

- [x] Dieser Kurs wurde aus MDX erzeugt.
- [ ] Dieser Kurs wurde manuell in Moodle geklickt.
:::
::::
```

Quiz-Attribute:

- `title`: Titel der Quiz-Aktivität.

Question-Attribute:

- `type`: aktuell `multichoice`.
- `name`: Moodle-Fragenname.
- `slot`: optionale Slotnummer.
- `page`: optionale Seitennummer.
- `defaultmark`, `penalty`, `maxmark`: optionale Bewertungswerte.
- `single`: aktuell typischerweise `true` für Einfachauswahl.
- `shuffleanswers`: ob Moodle Antworten mischen darf.
- `answernumbering`: optionale Moodle-Nummerierung.

Der Question-Body bis zur Antwortliste wird als `questiontext` geschrieben.
Antworten werden als Markdown-Liste notiert. `- [x]` wird als richtige Antwort
gerendert, `- [ ]` als falsche Antwort.

## Dateibasierte Aktivitäten

Folder und GeoGebra verwenden lokale Asset-Dateien. `files.xml` und die
`files/<sha1-prefix>/<sha1>`-Blobs werden aus diesen Dateien erzeugt.
Standalone-Dateien erhalten `userid=2`, `author=mdx2moodle` und
`license=allrightsreserved`, damit Moodle sie nach dem Restore zuverlässig den
Aktivitäten zuordnet.

### Folder

```mdx
:::folder{title="Material"}
<p>Materialien zum Download.</p>

- assets/material.pdf
:::
```

Der Body vor der Dateiliste wird als HTML in `folder/intro` geschrieben. Jede
Listenzeile referenziert eine lokale Datei.

### GeoGebra

```mdx
:::geogebra{title="GeoGebra" file="assets/geogebra.ggb" width=1040 height=640}
<p>Eine lokale GeoGebra-Datei.</p>
:::
```

GeoGebra-Attribute:

- `file`: lokale `.ggb`-Datei.
- `width`, `height`: optionale Größenwerte.

Der Body wird als HTML in `geogebra/intro` geschrieben. `geogebra/url` wird aus
dem Dateinamen des `file`-Attributs gesetzt. `.ggb`-Dateien werden als
`application/zip` in den Moodle-File-Pool geschrieben.

## Assign und Forum

Assign und Forum werden als einfache Aktivitäts-Directives geschrieben. Der Body
wird als HTML-Intro in die jeweilige XML geschrieben.

```mdx
:::assign{title="Reflexion" grade=100 submission_onlinetext=true submission_file=false feedback_comments=true}
<p>Beschreibe kurz, was du gelernt hast.</p>
:::

:::forum{title="Ankündigungen"}
<p>Ankündigungen und Nachrichten.</p>
:::
```

Assign-Attribute:

- `grade`, `gradingduedate`, `maxattempts`, `attemptreopenmethod`,
  `completionsubmit`: optionale Moodle-Settings.
- `submission_onlinetext`, `submission_file`, `submission_comments`,
  `feedback_comments`, `feedback_editpdf`: aktivieren oder deaktivieren die
  jeweiligen Plugin-Konfigurationen.

Forum nutzt aktuell keine speziellen Attribute über die gemeinsamen
Aktivitätsattribute hinaus.

## Minimalbeispiel

`examples/minimal/kurs.mdx` zeigt einen kleinen vollständigen Kurs mit Label,
Book, Quiz, Assign, Forum, Folder und GeoGebra. Er lässt sich ohne weitere
Vorlage validieren und bauen:

```bash
PYTHONPATH=src python3 -m moodle_mdx.cli validate examples/minimal/kurs.mdx
PYTHONPATH=src python3 -m moodle_mdx.cli build examples/minimal/kurs.mdx out/minimal.mbz --manifest out/minimal_manifest.json
```
