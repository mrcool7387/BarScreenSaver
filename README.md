# BarScreenSaver 📊🔊

Ein moderner, hochgradig anpassbarer **Audio-Visualizer und AFK-Screen** für Windows. Das Tool kombiniert Echtzeit-Audioanalyse mit Spotify-Integration und bietet eine ansprechende visuelle Darstellung deiner Musik direkt auf dem Desktop.

---

> [!IMPORTANT]
> **Systemanforderung:** Dieses Projekt ist für **Windows** optimiert. Es nutzt die Windows Core Audio APIs via `pycaw`, um den Systemsound direkt abzugreifen.

## ✨ Kern-Features

* [x] **Echtzeit-FFT Visualisierung:** Hochpräzise Frequenzanalyse für flüssige Balkenbewegungen.
* [x] **Spotify-Integration:** Zeigt automatisch den aktuellen Track und Interpreten an.
* [x] **Werbe-Filter:** Erkennt Werbung anhand von Keywords und blendet Visualisierungen/Texte entsprechend aus.
* [x] **Dynamische Gradients:** Unterstützung für animierte "Rainbow"-Effekte und weiche Farbübergänge.
* [x] **Smart Logging:** Detaillierte Fehleranalyse und Statusmeldungen durch die `Rich`-Bibliothek.
* [x] **Performance:** Optimiertes Threading für Audio-Capture, Spotify-Sync und GUI.

---

## 🚀 Schnellstart mit `uv`

Dieses Projekt nutzt [uv](https://docs.astral.sh/uv/) für ein modernes und extrem schnelles Paketmanagement.

### 1. Repository klonen

```bash
git clone https://github.com/dein-username/BarScreenSaver.git
cd BarScreenSaver
```

### 2. Umgebung synchronisieren

`uv` erstellt automatisch eine virtuelle Umgebung und installiert alle Abhängigkeiten aus der `pyproject.toml`:

```bash
uv sync
```

### 3. Anwendung starten

```bash
uv run main.py
```

---

## 🛠 Konfiguration

Die `config.json` ist das Herzstück für dein Design. Hier kannst du das Verhalten anpassen:

| Parameter          | Beschreibung                                  | Standard |
| ------------------ | --------------------------------------------- | -------- |
| `bar_count`        | Anzahl der Visualizer-Balken                  | `100`    |
| `smoothing`        | Glättung der Bewegung (höher = träger)        | `0.8`    |
| `gradient_dynamic` | Aktiviert die Farbanimation (Speed steuerbar) | `true`   |
| `gradient_speed`   | Geschwindigkeit des Farbwechsels              | `2.0`    |
| `show_clock`       | Zeigt eine digitale Uhr im Interface          | `true`   |

---

## 🎨 Eigene Farbschemata erstellen

Du kannst in der `config.json` unter dem Punkt `gradients` beliebig viele eigene Farbkombinationen hinzufügen. Ein Schema besteht immer aus einer Start- und einer Endfarbe (Hex-Code).

### Beispiel: Ein neues "Neon-Vibe" Schema hinzufügen

Öffne die `config.json` und füge dein Schema einfach am Ende der Liste hinzu:

```json
"gradients": {
    "spring": ["#FFB347", "#87CEEB"],
    "neon_vibe": ["#FF00FF", "#00FFFF"], 
    "matrix": ["#00FF00", "#003300"]
}
```

> [!TIP]
> Wenn `gradient_premaide` in der Config auf `true` steht, fragt das Programm dich beim Start, welches dieser Schemata du verwenden möchtest.

---

## ⚠️ Wichtige Hinweise

> [!WARNING]
> **Audio-Quelle:** Der Visualizer reagiert auf dein Standard-Wiedergabegerät. Wenn du kein Signal siehst, prüfe, ob in den Windows-Soundeinstellungen das richtige Gerät als "Standard" markiert ist.

> [!NOTE]
> **Erster Start:** Die Spotify-Integration öffnet ggf. ein Browserfenster zur Authentifizierung. Dies ist notwendig, damit die App deine aktuellen Player-Informationen lesen darf.

---

## 📂 Projektstruktur

* `main.py` - Hauptlogik, GUI-Steuerung und Audio-Verarbeitung.
* `_template.py` - Utility-Skript für automatisiertes Logging und Umgebungsprüfung.
* `_classes.py` - Definition von benutzerdefinierten Fehlermeldungen (z.B. `PyProjectError`).
* `config.json` - Zentrale Einstellungen für Optik und Features.
* `pyproject.toml` - Projekt-Metadaten und Abhängigkeiten (verwaltet via `uv`).

## 🗺 Roadmap

* [ ] Multi-Monitor Unterstützung (Full-Screen Toggle)
* [ ] Tray-Icon zum schnellen Wechseln der Profile
* [ ] Unterstützung für lokale Media-Player (AIMP, VLC)
* [ ] Audio-Input Wahl (Mikrofon statt Systemsound)

## 📄 Lizenz

Dieses Projekt steht unter der **MIT-Lizenz** – siehe die [LICENSE](https://www.google.com/search?q=LICENSE) Datei für Details.

---

**Entwickelt von Alexander Schwarz**
*Hast du Feedback oder einen Bug gefunden? Öffne gerne ein Issue im Repository!*
