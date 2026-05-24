import requests
import logging
import re

class GrocyApiClient:
    def __init__(self, base_url: str, port: str, api_key: str):
        self.frontend_url = f"{base_url.rstrip('/')}:{port}"
        self.base_url = f"{self.frontend_url}/api"
        self.headers = {
            "GROCY-API-KEY": api_key,
            "Accept": "application/json"
        }

    def get_inventory(self) -> list:
        """Holt den physischen Bestand inklusive Standorten, MHDs und Notizen."""
        logging.info("Lade Standorte...")
        loc_response = requests.get(f"{self.base_url}/objects/locations", headers=self.headers)
        location_map = {int(loc['id']): loc['name'] for loc in loc_response.json()}

        logging.info("Lade Produkt-Stammdaten...")
        prod_response = requests.get(f"{self.base_url}/objects/products", headers=self.headers)
        
        product_map = {}
        for p in prod_response.json():
            raw_desc = p.get('description', '') or ''
            clean_desc = re.sub(r'<[^>]+>', '', raw_desc).strip()
            product_map[int(p['id'])] = {
                "name": p['name'],
                "description": clean_desc
            }

        logging.info("Lade physischen Bestand (Splits, MHDs, Notizen)...")
        stock_response = requests.get(f"{self.base_url}/objects/stock", headers=self.headers)
        
        products = []
        for entry in stock_response.json():
            amount = float(entry.get('amount', 0))
            if amount <= 0:
                continue
                
            product_id = int(entry['product_id'])
            
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
                
            prod_data = product_map.get(product_id, {"name": f"Unbekannt ({product_id})", "description": ""})
                
            product_entry = {
                "id": product_id,
                "name": prod_data["name"],
                "description": prod_data["description"],
                "note": entry.get('note', '') or '',
                "available": amount,
                "opened": int(entry.get('open', 0)),
                "mhd": mhd_str,
                "location": location_map.get(int(entry['location_id']), "Unbekannter Ort") if entry.get('location_id') else "Kein Ort"
            }
            
            if not product_entry.get("note"): product_entry.pop("note", None)
            if not product_entry.get("description"): product_entry.pop("description", None)
            
            products.append(product_entry)

        return products