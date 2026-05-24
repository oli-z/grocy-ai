import sys, logging, os
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

logging.debug("Lade Libraries...")
import json, requests, datetime, hashlib, diskcache
from grocy import Grocy
from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel, Field
from typing import List, Literal

from prompts import WARNING_SYSTEM_PROMPT, WARNING_USER_PROMPT, RECIPE_SYSTEM_PROMPT, RECIPE_USER_PROMPT

logging.debug("Lade Konfig...")

GROCY_URL = os.getenv("GROCY_URL")
GROCY_PORT = os.getenv("GROCY_PORT")
GROCY_API_KEY = os.getenv("GROCY_API_KEY")

cache = diskcache.Cache('cache')
grocy = Grocy(GROCY_URL, GROCY_API_KEY, port=GROCY_PORT)

class ProductWarning(BaseModel):
    product_id: int
    product_name: str
    warning_severity: int = Field(..., ge=1, le=4, description="1=gering, 4=kritisch")
    warning_title: str
    warning_text: str
    warning_actions: List[Literal["umlagern", "verbrauchen", "einfrieren", "keine Aktion", "Logikfehler/Sinnhaftigkeit prüfen"]]

class AIResponseSchema(BaseModel):
    warnings: List[ProductWarning]
    description: str = Field(description="Zusammenfassende Beschreibung , wie du den aktuellen Bestand einschätzt, ob gerade viel da ist oder ob ich bald einkaufen muss, und welche generellen Empfehlungen du hast, die nicht in den Details bereits auftauchen.")

class Recipe(BaseModel):
    title: str
    description: str
    difficulty: Literal["einfach", "medium", "anspruchsvoll"]
    prep_time_minutes: int
    ingredients_from_stock: List[str] = Field(description="Zutaten, die ich bereits zu Hause habe und hier verwertet werden")
    ingredients_needed: List[str] = Field(description="Zutaten, die für das Rezept noch eingekauft werden müssen, Optionale bitte markieren")
    instructions: List[str] = Field(description="Schritt-für-Schritt-Anleitung")

class RecipeResponseSchema(BaseModel):
    recipes: List[Recipe]

def grocy_get_products():
    GROCY_BASE_URL = f"{GROCY_URL.rstrip('/')}:{GROCY_PORT}/api"
    headers = {
        "GROCY-API-KEY": GROCY_API_KEY,
        "Accept": "application/json"
    }

    logging.info("Lade Standorte...")
    loc_response = requests.get(f"{GROCY_BASE_URL}/objects/locations", headers=headers)
    location_map = {int(loc['id']): loc['name'] for loc in loc_response.json()}

    logging.info("Lade Produkt-Stammdaten...")
    prod_response = requests.get(f"{GROCY_BASE_URL}/objects/products", headers=headers)
    product_map = {int(p['id']): p['name'] for p in prod_response.json()}

    logging.info("Lade physischen Bestand (Splits & MHDs)...")
    # objects/stock liefert jede einzelne Charge/MHD als eigene Zeile!
    stock_response = requests.get(f"{GROCY_BASE_URL}/objects/stock", headers=headers)
    
    products = []
    for entry in stock_response.json():
        amount = float(entry.get('amount', 0))
        if amount <= 0:
            continue
            
        product_id = int(entry['product_id'])
        
        # MHD sauber formatieren
        raw_mhd = entry.get('best_before_date')
        if raw_mhd and raw_mhd.startswith("2999"): 
            mhd_str = "Kein MHD"
        elif raw_mhd:
            date_part = raw_mhd.split(" ")[0].split("-")
            if len(date_part) == 3:
                mhd_str = f"{date_part[2]}.{date_part[1]}.{date_part[0]}"
            else:
                mhd_str = raw_mhd
        else:
            mhd_str = "Kein MHD"
            
        product_entry = {
            "id": product_id,
            "name": product_map.get(product_id, f"Unbekannt ({product_id})"),
            "available": amount,
            "opened": entry.get('open', 0),
            "mhd": mhd_str,
            "location": location_map.get(int(entry['location_id']), "Unbekannter Ort") if entry.get('location_id') else "Kein Ort"
        }
        products.append(product_entry)

    return products

def get_ai_recommendations():
    stock_json_string = json.dumps(grocy_get_products(), indent=2, sort_keys=True, ensure_ascii=False)
    logging.debug(stock_json_string)
    stock_hash = hashlib.md5(stock_json_string.encode('utf-8')).hexdigest()
    
    cache_key = f"grocy_ai_warnings_{stock_hash}"    

    cached_response = cache.get(cache_key)
    if cached_response:
        logging.info("Ergebnis aus dem lokalen Datei-Cache geladen.")
        return cached_response

    logging.info("Cache abgelaufen oder nicht verügbar, frage AI ab...")
    logging.debug("Lade LiteLLM...")
    from litellm import completion

    AI_MODEL = os.getenv("AI_MODEL")

    messages = [
        {"role": "system", "content": WARNING_SYSTEM_PROMPT},
        {"role": "user", "content": WARNING_USER_PROMPT.format(stock_json_string=stock_json_string)}
    ]
    try:
        response = completion(
            model=AI_MODEL,
            messages=messages,
            response_format=AIResponseSchema
        )
        

        response_data = AIResponseSchema.model_validate_json(response.choices[0].message.content)
        response_data.warnings.sort(key=lambda x: x.warning_severity, reverse=True)
        
        # In den Cache schreiben
        cache.set(cache_key, response_data, expire=3600)
        return response_data

    except Exception as e:
        logging.error(f"❌ AI-API Fehler (z.B. Rate-Limit erreicht): {e}")
        # Fallback: Leeres Schema zurückgeben, damit der Report trotzdem generiert wird
        return AIResponseSchema(warnings=[])
    except Exception as e:
        # Fängt alle anderen unerwarteten Fehler ab
        logging.error(f"❌ Unerwarteter Fehler bei der AI-Abfrage: {e}")
        return AIResponseSchema(warnings=[])

def get_ai_recipes():
    stock_json_string = json.dumps(grocy_get_products(), indent=2, sort_keys=True, ensure_ascii=False)
    stock_hash = hashlib.md5(stock_json_string.encode('utf-8')).hexdigest()
    cache_key = f"grocy_ai_recipes_{stock_hash}"    

    cached_response = cache.get(cache_key)
    if cached_response:
        logging.info("Rezeptideen aus dem lokalen Datei-Cache geladen.")
        return cached_response

    logging.info("Generiere neue Rezeptideen mit der AI...")
    from litellm import completion

    AI_MODEL = os.getenv("AI_MODEL")

    try:
        response = completion(
            model=AI_MODEL,
            messages=[
                {"role": "system", "content": RECIPE_SYSTEM_PROMPT},
                {"role": "user", "content": RECIPE_USER_PROMPT.format(stock_json_string=stock_json_string)}
            ],
            response_format=RecipeResponseSchema
        )
        
        response_data = RecipeResponseSchema.model_validate_json(response.choices[0].message.content)
        cache.set(cache_key, response_data, expire=3600)
        return response_data

    except Exception as e:
        logging.error(f"❌ Fehler bei der Rezept-Generierung: {e}")
        return RecipeResponseSchema(recipes=[])

def generate_html_report():
    logging.info("Generiere statischen HTML-Report...")
    
    jinja_env = Environment(loader=FileSystemLoader('templates'))
    jinja_template = jinja_env.get_template('overview.html')
    jinja_data = {
        "ai_warnings": get_ai_recommendations(),
        "ai_recipes": get_ai_recipes(),
        "env": {
            "grocy_base_url": GROCY_URL + ":" + GROCY_PORT
        }
    }
    now = datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    rendered_html = jinja_template.render(
        data=jinja_data,
        timestamp=now
    )

    output_path = "output/index.html"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(rendered_html)
    
    logging.info(f"Erfolgreich generiert: {os.path.abspath(output_path)}")

generate_html_report()