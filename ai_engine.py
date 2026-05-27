import json
import hashlib
import logging
from litellm import completion

from models import AIResponseSchema, RecipeResponseSchema, ReceiptAnalysisSchema
from prompts import WARNING_SYSTEM_PROMPT, WARNING_USER_PROMPT, RECIPE_SYSTEM_PROMPT, RECIPE_USER_PROMPT, RECEIPT_SYSTEM_PROMPT

class AIEngine:
    def __init__(self, grocy_client, cache, ai_model: str):
        self.grocy = grocy_client
        self.cache = cache
        self.ai_model = ai_model

    def analyze_receipt(self, base64_image: str) -> dict:
        fields_needed = ["id", "name"]
        product_catalog = self.grocy.get_products(return_fields=fields_needed)

        catalog_json_str = json.dumps(product_catalog, ensure_ascii=False)
        
        prompt = RECEIPT_SYSTEM_PROMPT.format(product_catalog_json=catalog_json_str)
        response = completion(
            model=self.ai_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url", 
                            "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}
                        }
                    ]
                }
            ],
            response_format=ReceiptAnalysisSchema
        )
        
        return json.loads(response.choices[0].message.content)

    def get_recommendations(self, force_refresh: bool = False):
        stock_json_string = json.dumps(self.grocy.get_inventory(), indent=2, sort_keys=True, ensure_ascii=False)
        logging.debug(stock_json_string)
        stock_hash = hashlib.md5(stock_json_string.encode('utf-8')).hexdigest()
        
        cache_key = f"grocy_ai_warnings_{stock_hash}"    

        if not force_refresh:
            cached_response = self.cache.get(cache_key)
            if cached_response:
                logging.info("Warnungen aus dem lokalen Datei-Cache geladen.")
                return cached_response

        logging.info("Cache abgelaufen oder nicht verfügbar, frage AI ab...")
        
        messages = [
            {"role": "system", "content": WARNING_SYSTEM_PROMPT},
            {"role": "user", "content": WARNING_USER_PROMPT.format(stock_json_string=stock_json_string)}
        ]
        
        try:
            response = completion(
                model=self.ai_model,
                messages=messages,
                response_format=AIResponseSchema
            )
            
            response_data = AIResponseSchema.model_validate_json(response.choices[0].message.content)
            response_data.warnings.sort(key=lambda x: x.warning_severity, reverse=True)
            
            # In den Cache schreiben
            self.cache.set(cache_key, response_data, expire=3600)
            return response_data

        except Exception as e:
            logging.error(f"❌ Fehler bei der AI-Abfrage (Warnungen): {e}")
            return AIResponseSchema(warnings=[])

    def get_recipes(self, force_refresh: bool = False):
        stock_json_string = json.dumps(self.grocy.get_inventory(), indent=2, sort_keys=True, ensure_ascii=False)
        stock_hash = hashlib.md5(stock_json_string.encode('utf-8')).hexdigest()
        cache_key = f"grocy_ai_recipes_{stock_hash}"

        if not force_refresh:
            cached_response = self.cache.get(cache_key)
            if cached_response:
                logging.info("Rezeptideen aus dem lokalen Datei-Cache geladen.")
                return cached_response

        logging.info("Generiere neue Rezeptideen mit der AI...")

        try:
            response = completion(
                model=self.ai_model,
                messages=[
                    {"role": "system", "content": RECIPE_SYSTEM_PROMPT},
                    {"role": "user", "content": RECIPE_USER_PROMPT.format(stock_json_string=stock_json_string)}
                ],
                response_format=RecipeResponseSchema
            )
            
            response_data = RecipeResponseSchema.model_validate_json(response.choices[0].message.content)
            self.cache.set(cache_key, response_data, expire=3600)
            return response_data

        except Exception as e:
            logging.error(f"❌ Fehler bei der Rezept-Generierung: {e}")
            return RecipeResponseSchema(recipes=[])