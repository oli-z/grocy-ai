from config import GROCY_URL, GROCY_PORT, logging, cache, grocy
from ai_engine import AIEngine

logging.debug("Lade Libraries...")
import datetime, os
from jinja2 import Environment, FileSystemLoader

def generate_html_report():
    logging.info("Generiere statischen HTML-Report...")
    
    logging.info("Starte Generierung des Dashboards...")
    
    AI_MODEL = os.getenv("AI_MODEL")
    engine = AIEngine(grocy_client=grocy, cache=cache, ai_model=AI_MODEL)
    
    warnings_data = engine.get_recommendations()
    recipes_data = engine.get_recipes()

    jinja_env = Environment(loader=FileSystemLoader('templates'))
    jinja_template = jinja_env.get_template('overview.html')
    jinja_data = {
        "ai_warnings": warnings_data,
        "ai_recipes": recipes_data,
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