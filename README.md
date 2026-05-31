# grocy.AI

AI-gestützte Erweiterung für [Grocy](https://grocy.info/), die Bestandsprobleme erkennt, Rezeptideen generiert und Kassenbons automatisch einliest.

## Überblick

`grocy.AI` verbindet Grocy mit einem LLM-Backend (z. B. Gemini oder OpenAI) und liefert:

- **Bestandswarnungen** mit Priorisierung (z. B. bald ablaufende oder problematische Produkte - auch mit konkreten Handlungsempfehlungen)
- **Rezeptvorschläge** basierend auf verfügbarem Bestand
- **Kassenbon-Analyse** per Bildupload mit automatischer Zuordnung zu Grocy-Produkten
- Eine kleine **Web-Oberfläche** für die Anzeige von Warnungen, Rezepten und Receipt-Analyse

## Voraussetzungen

- Python 3 (getestet mit Python 3.14)
- Zugriff auf eine laufende Grocy-Instanz
- Ein AI-Modell (z. B. `gemini/gemini-2.5-flash`) oder ein kompatibler OpenAI-Endpoint (z.B. kostenlos über Google AI Studio)

## Installation

1. Repository klonen

2. .env anlegen (.env.example kann als Vorlage verwendet werden, siehe weiter unten für Konfiguration)

3. [nur lokale Installation] Abhängigkeiten installieren

```bash
pip install -r requirements.txt
```

## Starten

### Lokal

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Die Anwendung ist danach unter `http://localhost:8000` verfügbar.

### Mit Docker Compose

```bash
docker compose up
```

Die Konfiguration in `docker-compose.yml` veröffentlicht Port `8000`. In der .env kann ein eigener Port definiert werden.


## Konfigurationsoptionen
| Option | Beschreibung | erforderlich |
| --- | --- | --- |
| GROCY_API_KEY | API-Key für Zugriff auf Grocy | ja |
| GROCY_URL | Base-URL für Grocy ohne folgenden "/" | ja |
| GROCY_PORT | Port, auf welchem Grocy läuft | ja |

| AI_MODEL | das verwendete KI-Modell in einem Format für LiteLLM |
| GEMINI_API_KEY | API-Key je nach verwendetem Modell | je nach verwendetem Modell |
| OPENAI_API_KEY | API-Key je nach verwendetem Modell | je nach verwendetem Modell |
| LOG_LEVEL | Level der Logausgabe, z.B. "INFO" | nein |
| PORT | nur Docker: Port, auf welchem der Server exposed wird | ja |

## Projektstruktur

- `main.py` - FastAPI-App und API-Endpunkte
- `config.py` - Laden der Konfig und Initialisierung der Objekte
- `models.py` - definiert Pydantic-Models für strukturierten Code-Output des LLMs
- `ai_engine.py` - LLM-Integration, Caching und Analyse-Logik
- `grocy_client.py` - Grocy-API-Zugriff
- `prompts.py` - Prompt-Templates für Warnungen, Rezepte und Receipt-Analyse
- `static/` - Frontend

## Hinweise

- Ergebnisse werden lokal im Cache gespeichert, um wiederholte LLM-Abfragen zu reduzieren.
- Das Logfile wird in `logs/grocy_ai.log` geschrieben.