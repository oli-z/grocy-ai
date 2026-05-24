from aiohttp import request

from config import logging, cache, grocy
from models import AIResponseSchema, RecipeResponseSchema
from ai_engine import AIEngine

logging.debug("Lade Libraries...")
import datetime, os
from jinja2 import Environment, FileSystemLoader
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

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
            "grocy_base_url": grocy.frontend_url
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

app = FastAPI()
templates = Jinja2Templates(directory="templates")
engine = AIEngine(grocy_client=grocy, cache=cache, ai_model=os.getenv("AI_MODEL"))

# @app.get("/")
# async def dashboard(request: Request, refresh: bool = False):
#     warnings_data = engine.get_recommendations(force_refresh=refresh)
#     recipes_data = engine.get_recipes(force_refresh=refresh)
    
#     return templates.TemplateResponse(
#         request=request,
#         name="overview.html",
#         context={
#             "data": {
#                 "ai_warnings": warnings_data,
#                 "ai_recipes": recipes_data,
#                 "env": {"grocy_base_url": grocy.frontend_url}
#             }
#         }
#     )

@app.get("/api/warnings", response_model=AIResponseSchema)
async def api_get_warnings(refresh: bool = False):
    """Liefert nur die Warnungen als reines JSON zurück."""
    return engine.get_recommendations(force_refresh=refresh)

@app.get("/api/recipes", response_model=RecipeResponseSchema)
async def api_get_recipes(refresh: bool = False):
    """Liefert nur die Rezepte als reines JSON zurück."""
    return engine.get_recipes(force_refresh=refresh)

app.mount("/", StaticFiles(directory="static", html="index.html"), name="static")