from aiohttp import request

from config import logging, cache, grocy, get_config
from models import AIResponseSchema, RecipeResponseSchema
from ai_engine import AIEngine

logging.debug("Lade Libraries...")
import datetime, os, base64
from jinja2 import Environment, FileSystemLoader
from fastapi import FastAPI, Request, UploadFile, File, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

def generate_html_report():
    logging.info("Generiere statischen HTML-Report...")
    
    logging.info("Starte Generierung des Dashboards...")
    
    LLM_AI_MODEL = get_config("LLM_AI_MODEL")
    engine = AIEngine(grocy_client=grocy, cache=cache, ai_model=LLM_AI_MODEL)
    
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
engine = AIEngine(grocy_client=grocy, cache=cache, ai_model=get_config("LLM_AI_MODEL"), base_url=get_config("LLM_BASE_URL"), api_key=get_config("LLM_API_KEY"))

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

@app.get("/api/config")
async def api_get_config():
    """Liefert die Konfiguration als reines JSON zurück."""
    return {
        "llm_ai_model": get_config("LLM_AI_MODEL"),
        "llm_base_url": get_config("LLM_BASE_URL"),
        "grocy_base_url": get_config("GROCY_URL") + ":" + str(get_config("GROCY_PORT")),
    }

@app.post("/api/receipt/analyze")
async def analyze_receipt(file: UploadFile = File(...)):
    """
    Nimmt ein Bild des Kassenbons entgegen, wandelt es in Base64 um
    und lässt es durch die Gemini-Engine gegen den Grocy-Katalog prüfen.
    """
    if not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=400, 
            detail="Ungültiges Dateiformat. Bitte lade ein Bild (JPEG/PNG) hoch."
        )
    
    try:
        image_bytes = await file.read()
        base64_image = base64.b64encode(image_bytes).decode("utf-8")
        analysis_result = engine.analyze_receipt(base64_image)
        analysis_result["product_catalog"] = engine.grocy.get_products(return_fields=["id", "name"])
        return analysis_result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Fehler bei der Kassenbon-Analyse: {str(e)}"
        )

@app.post("/api/receipt/submit")
async def submit_receipt_analysis(analysis_result: dict):
    """
    Überträgt die Analyseergebnisse des Kassenbons an den Grocy-Katalog.
    """
    try:
        print("Zu übermittelnder Kassenbon:", analysis_result)
        products_added = []
        products_failed = []
        products_skipped = analysis_result.get("skipped_items", [])
        
        for item in analysis_result.get("items", []):
            try:
                grocy.add_product(product_id=item["mapped_product_id"], amount=item["amount"])
                product_name = item["receipt_name"]
                products_added.append({"name": product_name, "id": item["mapped_product_id"], "amount": item["amount"]})
            except Exception as e:
                products_failed.append({"name": item["receipt_name"], "error": str(e)})
        
        return {
            "status": "success",
            "added": products_added,
            "failed": products_failed,
            "skipped": products_skipped
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Fehler bei der Übertragung der Kassenbon-Analyse: {str(e)}"
        )

app.mount("/", StaticFiles(directory="static", html="index.html"), name="static")