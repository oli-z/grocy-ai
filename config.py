import sys, logging, os, diskcache
from dotenv import load_dotenv

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
GROCY_URL = os.getenv("GROCY_URL")
GROCY_PORT = os.getenv("GROCY_PORT")
GROCY_API_KEY = os.getenv("GROCY_API_KEY")

cache = diskcache.Cache('cache')