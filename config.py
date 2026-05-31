import sys, logging, os, diskcache, json
from dotenv import load_dotenv
from grocy_client import GrocyApiClient

load_dotenv()

LOG_LEVEL_STR = os.environ.get("LOG_LEVEL", "INFO").upper()
LOG_LEVEL = getattr(logging, LOG_LEVEL_STR, logging.INFO)

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%d.%m.%Y %H:%M:%S",
    handlers=[
        logging.FileHandler("logs/grocy_ai.log", encoding="utf-8"), # In Datei schreiben
        logging.StreamHandler(sys.stdout)                             # Auf Konsole ausgeben
    ]
)

logging.info(f"Logging initialisiert mit Level: {logging.getLevelName(LOG_LEVEL)}")

logging.debug("Lade Konfig...")

HA_OPTIONS_PATH = "/data/options.json"

def get_config(key: str, default=None) -> str:
    """
    Lade Config:
    1. Zuerst in der Home Assistant options.json (alles klein geschrieben), falls es als HA App läuft
    2. Danach in den Umgebungsvariablen / .env (alles GROSS geschrieben)
    """
    # 1. Versuch: Home Assistant Add-on Umgebung
    if os.path.exists(HA_OPTIONS_PATH):
        try:
            with open(HA_OPTIONS_PATH, "r") as f:
                ha_options = json.load(f)
                # Home Assistant speichert Keys im JSON immer klein (z.b. gemini_api_key)
                ha_key = key.lower()
                if ha_key in ha_options and ha_options[ha_key] != "":
                    return ha_options[ha_key]
        except Exception as e:
            logging.error(f"Fehler beim Lesen der HA Optionen: {e}")

    # 2. Versuch: Umgebungsvariable (z.b. GEMINI_API_KEY)
    env_key = key.upper()
    return os.getenv(env_key, default)

GROCY_URL = get_config("GROCY_URL")
GROCY_PORT = get_config("GROCY_PORT")
GROCY_API_KEY = get_config("GROCY_API_KEY")

cache = diskcache.Cache('cache')
grocy = GrocyApiClient(GROCY_URL, GROCY_PORT, GROCY_API_KEY)