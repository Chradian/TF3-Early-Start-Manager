# TF3 Early Start Manager

**Start Transport Fever 3 in 1850 and manage Early Start compatibility without manually editing game files.**

TF3 Early Start Manager is a community tool for players who want to begin Transport Fever 3 much earlier than the regular starting period. It handles the required game patch, compatibility overrides and resource analysis through a graphical interface and keeps the process reversible through backups.

> **Current release:** 1.0.0  
> **Platform:** Windows 10/11 x64  
> **Tested with:** Transport Fever 3 on Steam  
> **License:** GNU GPL v3.0

#english | #deutsch

---

# English

## Features

- Start **Transport Fever 3 in 1850**
- Automatic Transport Fever 3 installation detection
- Safe Early Start GUI patch with backup and restore
- Detection of Transport Fever 3 game/build updates
- Automatic Early Start Compatibility Mod generation
- **24 mandatory Early Start compatibility overrides**
- Resource Browser for inspecting TF3 content
- Detection and analysis of:
  - Vanilla content
  - Mod.io content
  - Local mods
- Easy Mode for normal use
- Advanced Mode for detailed resource management and diagnostics
- Multi-language user interface
- Portable Windows application
- No separate Python installation required
- Integrated logging and cache system

## Download

Download the latest packaged Windows version from the **Releases** section of this repository.

## Installation

1. Download `TF3_Early_Start_Manager_v1.0.0_Windows_x64.zip`.
2. Extract the complete ZIP archive to a folder of your choice.
3. Start `TF3 Early Start Manager.exe`.
4. Let the manager detect your Transport Fever 3 installation.
5. Follow the status indicators to install/update the Early Start patch and Compatibility Mod.
6. Start Transport Fever 3 through the manager or normally through your game platform.

Do not run the executable directly from inside the ZIP archive.

### Portable application

TF3 Early Start Manager is distributed as a portable Windows application.

No installer and no separate Python or PySide6 installation are required.

The complete release folder can be moved to another location. Always keep the executable together with its `_internal` directory.

Runtime data such as cache and logs is created next to the executable.

## What the manager changes

TF3 Early Start Manager can modify game resources required to enable the earlier start date and can generate a Compatibility Mod containing required Early Start overrides.

The manager is designed to keep these changes manageable and reversible:

- Game modifications are backed up before patching.
- Patch state is verified by the manager.
- The original game state can be restored.
- Compatibility overrides are generated separately as a mod.
- TF3 build/version changes are detected so compatibility can be checked again after an update.

### Important

A Transport Fever 3 update may replace or change files used by the Early Start patch.

After a TF3 update, open TF3 Early Start Manager and check the reported compatibility status before continuing an existing Early Start game.

Keeping normal backups of important Transport Fever 3 savegames is strongly recommended.

## Compatibility

### Tested

| Platform / Store | Status |
|---|---|
| Windows 10/11 x64 | ✅ Supported |
| Steam | ✅ Tested |
| Transport Fever 3 Early Start 1850 | ✅ Tested |
| Portable Windows build | ✅ Tested |

### Testing wanted

| Platform / Store | Status |
|---|---|
| Epic Games Store | 🧪 Testing wanted |
| GOG | 🧪 Testing wanted |
| Linux | ⏳ No packaged release yet |
| macOS | ⏳ No packaged release yet |

## To Do / Community Testing

### Epic Games Store & GOG testers wanted

Installation detection for additional storefronts is implemented, but the initial 1.0.0 release has primarily been validated with the **Steam version of Transport Fever 3**.

If you own Transport Fever 3 on the **Epic Games Store** or **GOG**, testing and feedback are especially welcome.

Please test, where possible:

- automatic TF3 installation detection
- game build/version detection
- Early Start patch installation
- patch verification
- backup and restore
- Compatibility Mod generation
- mandatory Early Start overrides
- game launching from the manager

If something does not work, please create a GitHub Issue and include:

- TF3 Early Start Manager version
- Transport Fever 3 build number
- store/platform, for example Steam, Epic or GOG
- description of the expected and actual behaviour
- relevant manager log output

### Future areas

Potential future work includes:

- broader Epic Games Store validation
- broader GOG validation
- investigation of Linux support
- investigation of macOS support
- additional compatibility testing after TF3 updates
- continued resource-classification improvements based on real TF3 and mod content

## Resource Browser

Advanced Mode contains a Resource Browser for inspecting discovered Transport Fever 3 resources.

The manager can analyse content from multiple sources, including:

- Transport Fever 3 Vanilla resources
- Mod.io mods
- locally installed mods

Resource classification is based on actual TF3 resource information rather than relying only on folder names.

The Resource Browser is primarily intended for advanced users, mod users and diagnostics. Normal Early Start use does not require manual resource management.

## Easy Mode and Advanced Mode

### Easy Mode

Designed for normal Early Start use.

Easy Mode focuses on:

- TF3 installation status
- Early Start patch status
- Compatibility Mod status
- compatibility warnings
- starting the game

### Advanced Mode

Designed for users who want additional control and diagnostics.

Advanced Mode provides access to:

- resource scanning
- Resource Browser
- detailed compatibility information
- cache/log information
- additional configuration and diagnostic functions

## Reporting bugs

Please use the **Issues** section of this GitHub repository for reproducible problems.

Useful information includes:

- TF3 Early Start Manager version
- Transport Fever 3 build number
- Windows version
- Steam / Epic Games Store / GOG
- steps required to reproduce the issue
- expected behaviour
- actual behaviour
- relevant manager logs

Please remove personal paths or other private information from logs before posting them publicly if necessary.

## Building from source

The repository contains the source code and the reproducible PyInstaller build configuration used for the Windows distribution.

### Requirements

- Windows
- Python
- PySide6
- PyInstaller

The tested 1.0.0 build environment uses the versions documented in:

`requirements.txt`

and:

`requirements-build.txt`

### Create a virtual environment

```powershell
python -m venv .venv
```

Install the required packages:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-build.txt
```

### Build

The repository contains:

`TF3 Early Start Manager.spec`

and:

`build_release.ps1`

Run:

```powershell
.\build_release.ps1
```

The release build is created using the included PyInstaller specification.

Do not commit generated `build`, `dist`, cache or log directories to the repository.

## Disclaimer

TF3 Early Start Manager is an independent community project.
It is **not affiliated with, endorsed by, sponsored by or officially supported by Urban Games or the developers/publishers of Transport Fever 3**.
Transport Fever and Transport Fever 3 are trademarks or properties of their respective rights holders.
Use of the manager and modifications to local game files are at the user's own responsibility.

## AI-assisted development

TF3 Early Start Manager was developed with substantial assistance from AI-based development tools.
Project direction, feature decisions, integration, hands-on testing and release validation were performed by the project author.

## License

Copyright © 2026 Christian Walter

TF3 Early Start Manager is licensed under the **GNU General Public License v3.0**.

See the `LICENSE` file for the complete license text.

---

# Deutsch

## Über das Projekt

**TF3 bereits 1850 starten und die dafür notwendige Early-Start-Kompatibilität verwalten, ohne Spieldateien manuell bearbeiten zu müssen.**

Der TF3 Early Start Manager ist ein Community-Tool für Spieler, die Transport Fever 3 deutlich früher als im regulären Spiel beginnen möchten.

Der Manager übernimmt den notwendigen Patch, Compatibility Overrides und die Analyse von TF3-Ressourcen über eine grafische Oberfläche. Durch Backups und Statusprüfungen bleiben die Änderungen nachvollziehbar und rückgängig zu machen.

> **Aktueller Release:** 1.0.0  
> **Plattform:** Windows 10/11 x64  
> **Getestet mit:** Transport Fever 3 über Steam  
> **Lizenz:** GNU GPL v3.0

## Funktionen

- **Transport Fever 3 ab 1850 starten**
- Automatische Erkennung der Transport-Fever-3-Installation
- Sicherer Early-Start-GUI-Patch mit Backup und Wiederherstellung
- Erkennung von Transport-Fever-3-Spiel-/Build-Updates
- Automatische Erstellung des Early Start Compatibility Mods
- **24 verpflichtende Early-Start-Compatibility-Overrides**
- Resource Browser zur Untersuchung von TF3-Inhalten
- Erkennung und Analyse von:
  - Vanilla-Inhalten
  - Mod.io-Inhalten
  - lokalen Mods
- Easy Mode für die normale Nutzung
- Advanced Mode für detaillierte Ressourcenverwaltung und Diagnose
- Mehrsprachige Benutzeroberfläche
- Portable Windows-Anwendung
- Keine separate Python-Installation erforderlich
- Integriertes Log- und Cache-System

## Download

Die aktuelle fertige Windows-Version befindet sich im Bereich **Releases** dieses GitHub-Repositories.

## Installation

1. `TF3_Early_Start_Manager_v1.0.0_Windows_x64.zip` herunterladen.
2. Das komplette ZIP-Archiv in einen beliebigen Ordner entpacken.
3. `TF3 Early Start Manager.exe` starten.
4. Die Transport-Fever-3-Installation automatisch erkennen lassen.
5. Den Statusanzeigen folgen und Early-Start-Patch sowie Compatibility Mod installieren bzw. aktualisieren.
6. Transport Fever 3 über den Manager oder normal über die jeweilige Spieleplattform starten.

Die Anwendung nicht direkt aus dem ZIP-Archiv heraus starten.

### Portable Anwendung

Der TF3 Early Start Manager wird als portable Windows-Anwendung ausgeliefert.

Es wird kein Installer benötigt. Python und PySide6 müssen ebenfalls nicht separat installiert sein.

Der komplette Release-Ordner kann an einen anderen Speicherort verschoben werden. Die EXE muss dabei immer zusammen mit dem `_internal`-Ordner verschoben werden.

Runtime-Daten wie Cache und Logs werden neben der Anwendung angelegt.

## Was verändert der Manager?

Der TF3 Early Start Manager kann Spielressourcen verändern, die für den früheren Spielstart erforderlich sind, und einen Compatibility Mod mit den notwendigen Early-Start-Overrides erzeugen.

Der Manager wurde so entwickelt, dass diese Änderungen kontrollierbar und rückgängig zu machen sind:

- Vor dem Patchen werden Backups erstellt.
- Der Patch-Zustand wird überprüft.
- Der ursprüngliche Zustand kann wiederhergestellt werden.
- Compatibility Overrides werden separat als Mod erzeugt.
- Änderungen der TF3-Spielversion werden erkannt, damit die Kompatibilität nach einem Update erneut überprüft werden kann.

### Wichtig

Ein Update von Transport Fever 3 kann Dateien ersetzen oder verändern, die vom Early-Start-Patch verwendet werden.

Nach einem TF3-Update sollte deshalb zuerst der TF3 Early Start Manager geöffnet und der gemeldete Kompatibilitätsstatus geprüft werden, bevor ein bestehendes Early-Start-Spiel fortgesetzt wird.

Unabhängig davon werden normale Backups wichtiger Transport-Fever-3-Spielstände dringend empfohlen.

## Kompatibilität

### Getestet

| Plattform / Store | Status |
|---|---|
| Windows 10/11 x64 | ✅ Unterstützt |
| Steam | ✅ Getestet |
| Transport Fever 3 Early Start 1850 | ✅ Getestet |
| Portable Windows-Version | ✅ Getestet |

### Tests gesucht

| Plattform / Store | Status |
|---|---|
| Epic Games Store | 🧪 Tester gesucht |
| GOG | 🧪 Tester gesucht |
| Linux | ⏳ Noch kein fertiger Release |
| macOS | ⏳ Noch kein fertiger Release |

## To-do / Community-Tests

### Tester für Epic Games Store & GOG gesucht

Die Erkennung zusätzlicher Store-Versionen ist implementiert. Der erste Release 1.0.0 wurde jedoch hauptsächlich mit der **Steam-Version von Transport Fever 3** getestet.

Wenn du Transport Fever 3 über den **Epic Games Store** oder **GOG** besitzt, sind Tests und Feedback besonders willkommen.

Interessant sind insbesondere:

- automatische Erkennung der TF3-Installation
- Erkennung der Spiel-/Build-Version
- Installation des Early-Start-Patches
- Überprüfung des Patch-Zustands
- Backup und Wiederherstellung
- Erstellung des Compatibility Mods
- verpflichtende Early-Start-Overrides
- Spielstart über den Manager

Falls etwas nicht funktioniert, bitte ein GitHub Issue erstellen und möglichst folgende Informationen angeben:

- Version des TF3 Early Start Managers
- TF3-Buildnummer
- Store/Plattform, beispielsweise Steam, Epic oder GOG
- erwartetes Verhalten
- tatsächliches Verhalten
- relevante Ausschnitte aus dem Manager-Log

### Mögliche zukünftige Themen

- umfassendere Tests mit dem Epic Games Store
- umfassendere Tests mit GOG
- Untersuchung einer Linux-Version
- Untersuchung einer macOS-Version
- weitere Kompatibilitätstests nach TF3-Updates
- weitere Verbesserungen der Ressourcenklassifizierung anhand realer TF3- und Mod-Ressourcen

## Resource Browser

Der Advanced Mode enthält einen Resource Browser zur Untersuchung erkannter Transport-Fever-3-Ressourcen.

Der Manager kann Inhalte aus verschiedenen Quellen analysieren:

- Transport Fever 3 Vanilla
- Mod.io-Mods
- lokal installierte Mods

Die Klassifizierung basiert auf tatsächlichen TF3-Ressourceninformationen und nicht ausschließlich auf Verzeichnisnamen.

Der Resource Browser richtet sich hauptsächlich an fortgeschrittene Nutzer, Mod-Nutzer und Diagnosezwecke. Für die normale Verwendung des Early Starts ist keine manuelle Ressourcenverwaltung erforderlich.

## Easy Mode und Advanced Mode

### Easy Mode

Für die normale Early-Start-Nutzung.

Der Easy Mode konzentriert sich auf:

- Status der TF3-Installation
- Status des Early-Start-Patches
- Status des Compatibility Mods
- Kompatibilitätswarnungen
- Start des Spiels

### Advanced Mode

Für zusätzliche Kontrolle und Diagnose.

Der Advanced Mode bietet unter anderem:

- Resource Scanning
- Resource Browser
- detaillierte Kompatibilitätsinformationen
- Cache-/Log-Informationen
- zusätzliche Konfigurations- und Diagnosefunktionen

## Fehler melden

Für reproduzierbare Probleme bitte den Bereich **Issues** dieses GitHub-Repositories verwenden.

Hilfreiche Informationen sind:

- Version des TF3 Early Start Managers
- Transport-Fever-3-Buildnummer
- Windows-Version
- Steam / Epic Games Store / GOG
- Schritte zum Reproduzieren
- erwartetes Verhalten
- tatsächliches Verhalten
- relevante Manager-Logs

Private Pfade oder andere persönliche Informationen sollten bei Bedarf aus Logs entfernt werden, bevor diese öffentlich gepostet werden.

## Aus dem Source Code bauen

Das Repository enthält den Source Code sowie die reproduzierbare PyInstaller-Konfiguration für den Windows-Build.

### Voraussetzungen

- Windows
- Python
- PySide6
- PyInstaller

Die für Version 1.0.0 getesteten Abhängigkeiten sind dokumentiert in:

`requirements.txt`

und:

`requirements-build.txt`

### Virtuelle Umgebung erstellen

```powershell
python -m venv .venv
```

Abhängigkeiten installieren:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-build.txt
```

### Build erstellen

Das Repository enthält:

`TF3 Early Start Manager.spec`

und:

`build_release.ps1`

Ausführen:

```powershell
.\build_release.ps1
```

Der Release-Build wird anschließend anhand der mitgelieferten PyInstaller-Spezifikation erzeugt.

Generierte `build`-, `dist`-, Cache- und Log-Verzeichnisse gehören nicht ins Repository.

## Haftungsausschluss

TF3 Early Start Manager ist ein unabhängiges Community-Projekt.
Das Projekt ist **weder mit Urban Games verbunden noch von Urban Games oder den Entwicklern/Publishern von Transport Fever 3 unterstützt, gesponsert oder offiziell freigegeben**.
Transport Fever und Transport Fever 3 sind Marken bzw. Eigentum der jeweiligen Rechteinhaber.
Die Verwendung des Managers und Änderungen an lokalen Spieldateien erfolgen auf eigene Verantwortung.

## KI-unterstützte Entwicklung

Der TF3 Early Start Manager wurde mit umfangreicher Unterstützung durch KI-basierte Entwicklungswerkzeuge entwickelt.
Projektausrichtung, Funktionsentscheidungen, Integration, praktische Tests und Release-Validierung wurden durch den Projektentwickler durchgeführt.

## Lizenz

Copyright © 2026 Christian Walter

Der TF3 Early Start Manager steht unter der **GNU General Public License v3.0**.

Der vollständige Lizenztext befindet sich in der Datei `LICENSE`.
