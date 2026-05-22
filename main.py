import sys, logging

logging.basicConfig(
    level=logging.DEBUG, # Minimales Log-Level (alles darunter, wie DEBUG, wird ignoriert)
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%d.%m.%Y %H:%M:%S",
    handlers=[
        logging.FileHandler("logs/grocy_ai.log", encoding="utf-8"), # In Datei schreiben
        logging.StreamHandler(sys.stdout)                             # Auf Konsole ausgeben
    ]
)

logging.debug("Lade Libraries...")
import os, json, requests, datetime, hashlib, diskcache
from dotenv import load_dotenv
from grocy import Grocy
from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel, Field
from typing import List, Literal

logging.debug("Lade Konfig...")
load_dotenv()

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

# def grocy_get_products():
#     GROCY_BASE_URL = f"{GROCY_URL.rstrip('/')}:{GROCY_PORT}/api"
#     headers = {
#         "GROCY-API-KEY": GROCY_API_KEY,
#         "Accept": "application/json"
#     }

#     logging.info("Lade Standorte...")
#     loc_response = requests.get(f"{GROCY_BASE_URL}/objects/locations", headers=headers)
#     if loc_response.status_code != 200:
#         print(f"Fehler beim Laden der Standorte: {loc_response.status_code}")
#         exit(1)

#     location_map = {int(loc['id']): loc['name'] for loc in loc_response.json()}

#     logging.info("Lade Produkte...")
#     products = []
#     for product in grocy.stock.current():
#         product2 = {}
#         product2["id"] = product.id
#         product2['name'] = product.name
#         product2['available'] = product.available_amount
#         product2['opened'] = product.amount_opened
#         product2['mhd'] = product.best_before_date.strftime("%d.%m.%Y")
#         product2['location'] = location_map.get(int(product.location_id), "Unbekannter Ort") if product.location_id else "Kein Ort"
#         products.append(product2)
#         #print(f"{product.name}: {product.available_amount} in stock")

#     return products

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

    system_instruction = (
        "Du bist ein smarter Küchenchef und vorausschauender Lager-Logistiker. "
        "Analysiere den folgenden Lebensmittelbestand nach diesen strengen Kriterien:\n\n"
        "1. Realistische Verzehrmenge: Schaue dir die verfügbare Menge ('available') im Verhältnis zum MHD an. "
        "Beurteile realistisch, ob ein Haushalt diese Menge vor dem Verderb überhaupt aufessen kann. "
        "Wenn die Menge zu groß für den sofortigen Verzehr ist, dränge nicht auf 'verbrauchen'.\n"
        "2. Strategisches Einfrieren vorziehen: 'verbrauchen' hat NICHT automatisch die höchste Priorität. "
        "Wenn ein Produkt das Einfrieren ohne nennenswerten Qualitätsverlust verträgt (z.B. Fleisch, Brot, roher Fisch, bestimmte Backwaren), "
        "schlage ohne Zögern 'einfrieren' vor, um den Verzehr-Stress aus der Woche zu nehmen.\n"
        "3. Gefrier-Nachteile im Text erwähnen: Integriere in das Feld 'warning_text' IMMER einen konkreten Satz "
        "darüber, wie gut das Produkt das Einfrieren verträgt und ob es Nachteile gibt. "
        "Beispiele:\n"
        "- 'Lässt sich ohne Qualitätsverlust einfrieren.'\n"
        "- 'Einfrieren verändert die Textur (wird weich), danach aber perfekt für Saucen/Suppen geeignet.'\n"
        "- 'Einfrieren nicht empfohlen, da das Produkt ausflockt/wässrig wird.'\n"
        "4. Fokus: Keine Rezepte, nur logistische Handlungsempfehlungen."
    )

    user_prompt = f""" Hier ist mein aktueller Küchenbestand im JSON-Format:

    <inventory>
    {stock_json_string}
    </inventory>

    Was sind deine konkreten Warnungen/Empfehlungen?"""

    messages = [
        {"role": "system", "content": system_instruction},
        {"role": "user", "content": user_prompt}
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


def generate_html_report():
    logging.info("Generiere statischen HTML-Report...")
    
    jinja_env = Environment(loader=FileSystemLoader('templates'))
    jinja_template = jinja_env.get_template('overview.html')
    jinja_data = {
        "ai_warnings": get_ai_recommendations(),
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