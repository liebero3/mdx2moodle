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
PYTHONPATH=src python3 -m moodle_mdx.cli inspect-mbz out/minimal.mbz
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

Eine top-level H2-Überschrift erzeugt eine Moodle-Subsection. Sie wird als
`subsection`-Aktivität in der vorherigen Section und als verknüpfte Moodle-
Section mit `component=mod_subsection` gerendert. Die Subsection ist in v1 ein
leerer Strukturmarker; nachfolgende Directives bleiben in der vorherigen
Section. H2-Überschriften innerhalb von Directive-Blöcken bleiben normaler
Body-Inhalt.

```mdx
## Neuer Unterabschnitt
```

Optionale Attribute:

- `id`: Section-ID der verknüpften Subsection-Section im Autorenmodell.
- `item_id` oder `itemid`: stabile ID der erzeugten `subsection`-Aktivität.
- `index`: Moodle-Abschnittsnummer der verknüpften Section.
- `moodle_title`: Moodle-Anzeigetitel, falls er vom H2-Text abweichen soll.

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
Standalone-Dateien erhalten `userid=2`, `author=Moodle MDX` und
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

## Choice, Questionnaire und Board

Diese Typen bilden die in den Moodle-4.5.10-Referenzsicherungen sichtbaren
Aktivitätsstrukturen ab.

### Choice

```mdx
:::choice{title="Abstimmung" allowmultiple=true limitanswers=true timeopen=1778074560 timeclose=1778852160}
<p>Beschreibung</p>

- O1 {maxanswers=1}
- O2 {maxanswers=2}
:::
```

Der Body vor der Optionsliste wird als `choice/intro` geschrieben. Jede
Listenzeile erzeugt eine Option; `maxanswers` ist optional und zählt sonst ab
`1` hoch.

Wichtige Attribute:

- `allowmultiple`, `limitanswers`, `allowupdate`, `showunanswered`,
  `showpreview`, `showavailable`: boolesche Moodle-Settings.
- `timeopen`, `timeclose`: optionale Moodle-Zeitstempel.

### Questionnaire

```mdx
::::questionnaire{title="Befragung" opendate=1778074800 closedate=1778247600 survey_info="<p>Beschreibung/Zusatzinfos</p>" thank_head="Danke"}
<p>Beschreibung</p>

:::q{type="sectiontext" name="Hinweis"}
<h3>Einführung</h3>
:::

:::q{type="radio" name="Tempo" required=true}
<p>Wie war das Tempo?</p>

- Zu langsam
- Genau richtig
- Zu schnell
:::

:::q{id="schule_spass" type="radio" name="Macht dir Schule Spaß?" required=true length=1}
<p>Macht dir Schule Spaß?</p>

- Ja {id="ja"}
- Nein {id="nein"}
:::

:::q{id="warum_nicht" type="textarea" name="Warum nicht?" length=40 precise=5 depends_on="schule_spass:nein"}
<p>Warum macht dir Schule im Moment keinen Spaß?</p>
:::

:::q{id="checkboxen" type="checkbox" name="Auswahl"}
<p>Wähle passende Optionen.</p>

- Option A {id="option_a"}
- Option B {id="option_b"}
:::

:::q{id="datum" type="date" name="Datum" required=true depends_on="checkboxen:option_b"}
<p>Wähle ein Datum.</p>
:::

:::q{type="slider" name="Stimmung" minrange=-3 maxrange=3 startingvalue=0 stepvalue=1 leftlabel="schlecht" centerlabel="neutral" rightlabel="gut"}
<p>Wie schätzt du deine Stimmung ein?</p>
:::
::::
```

Der Body vor den `q`-Blöcken wird als `questionnaire/intro` geschrieben.
`survey_info`, `thanks_page`, `thank_head` und `thank_body` setzen die
Survey-Zusatzfelder.

Fragen werden als verschachtelte `:::q`-Blöcke geschrieben. Unterstützte
`type`-Werte:

- `sectiontext`: Beschriftung/Hinweistext (`type_id=100`)
- `pagebreak`: Seitenumbruch (`type_id=99`)
- `rate`: Skala 1-x (`type_id=8`, `length` setzt die Skalenlänge)
- `checkbox`: Checkboxen (`type_id=5`)
- `date`: Datum (`type_id=9`)
- `dropdown`: Dropdownfeld (`type_id=6`)
- `yesno`: Ja/Nein (`type_id=1`)
- `radio`: Radio-Auswahl (`type_id=4`)
- `slider`: Schieberegler (`type_id=11`)
- `text`: kurze Texteingabe (`type_id=3`)
- `textarea`: längeres Textfeld (`type_id=2`)

Gemeinsame Frage-Attribute:

- `name`: interner Moodle-Fragenname.
- `id`: stabile Autoren-ID, die andere Fragen referenzieren können.
- `required`: `true` schreibt `required=y`.
- `length`, `precise`, `position`: direkte Moodle-Felder.
- `depends_on`: optionale Anzeige-Logik im Format `frage:antwort`, z.B.
  `depends_on="checkboxen:option_b"`.
- `depends_join`: optional `and` oder `or`; bei mehreren Bedingungen auch als
  kommagetrennte Liste passend zu `depends_on`.
- `depends_logic`: optionales Moodle-Logikfeld; Default ist `1`. Bei mehreren
  Bedingungen kann es wie `depends_join` kommagetrennt geschrieben werden.

Choice-basierte Fragen (`rate`, `checkbox`, `dropdown`, `radio`) verwenden
Listenzeilen als `quest_choice`-Einträge. Antwortzeilen können ebenfalls ein
`id` tragen, damit sie in `depends_on` referenziert werden können. Slider
unterstützt `minrange`, `maxrange`, `startingvalue`, `stepvalue`, `leftlabel`,
`centerlabel` und `rightlabel`; daraus wird das Moodle-`extradata`-JSON
erzeugt.

Beim Build werden `depends_on`-Referenzen zu Moodle-`quest_dependencies`
aufgelöst. Unbekannte Frage- oder Antwort-IDs führen zu einem Build-Fehler,
damit keine unvollständige Logik in die Sicherung geschrieben wird.

Für Roundtrips aus vorhandenen Moodle-Sicherungen kann der Extractor
synthetische IDs wie `q5` und `c2` erzeugen, wenn im Original keine
Autoren-IDs existieren. Für neu geschriebene Kurse sind sprechende IDs wie
`schule_spass:nein` vorzuziehen.

### Board

```mdx
:::board{title="Board" background_color="bdb7ff" sortby=3}
<p>Beschreibung</p>

- Überschrift1
  - Karte mit **Markdown** und *Hervorhebung* {heading="Start"}
- Überschrift2
- Überschrift3
:::
```

Der Body vor der Spaltenliste wird als `board/intro` geschrieben. Jede
nicht eingerückte Listenzeile erzeugt eine Board-Spalte in dieser Reihenfolge.
Eingerückte Listenpunkte unter einer Spalte erzeugen optionale Seed-Karten.
Diese Karten sind im Moodle-Plugin Userdaten; wenn ein Board Seed-Karten
enthält, setzt der Builder für dieses Board das Activity-Setting
`board_<moduleid>_userinfo=1`.

Seed-Karten unterstützen in v1 reine Textkarten (`type=0`). Der Listeninhalt
wird unverändert als `content` geschrieben; `heading` ist optional. Das
Moodle-Board-Plugin rendert Markdown in diesem Feld selbst, deshalb bleiben
Markdown-Zeichen wie `#`, `**fett**`, `*kursiv*` oder Listenmarker im
Backup-Inhalt erhalten.

Die kompakte Listen-Syntax unterstützt aktuell einzeilige Seed-Karten. Für
umfangreichere mehrzeilige Karten kann der Markdown-Inhalt zunächst mit
HTML-Zeilenumbrüchen oder als einzeilige Markdown-Notation geschrieben werden;
eine eigene mehrzeilige `note`-Directive ist bewusst noch nicht Teil dieses
Dialekts.

## Minimalbeispiel

`examples/minimal/kurs.mdx` zeigt einen kleinen vollständigen Kurs mit Label,
Book, Quiz, Assign, Forum, Folder, GeoGebra, Subsection, Choice,
Questionnaire und Board. Er lässt sich ohne weitere Vorlage validieren und
bauen:

```bash
PYTHONPATH=src python3 -m moodle_mdx.cli validate examples/minimal/kurs.mdx
PYTHONPATH=src python3 -m moodle_mdx.cli build examples/minimal/kurs.mdx out/minimal.mbz --manifest out/minimal_manifest.json
PYTHONPATH=src python3 -m moodle_mdx.cli inspect-mbz out/minimal.mbz
```

Weitere CLI-Befehle:

```bash
PYTHONPATH=src python3 -m moodle_mdx.cli extract-mdx kurs.mbz out/extracted/kurs.mdx
PYTHONPATH=src python3 -m moodle_mdx.cli compare referenz.mbz out/minimal.mbz
```
