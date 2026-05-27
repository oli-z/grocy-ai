from pydantic import BaseModel, Field
from typing import List, Literal

class ProductWarning(BaseModel):
    product_id: int
    product_name: str
    warning_severity: int = Field(..., ge=1, le=4, description="1=gering, 4=kritisch")
    warning_title: str
    warning_text: str
    warning_actions: List[Literal["umlagern", "verbrauchen", "einfrieren", "keine Aktion", "Logikfehler/Sinnhaftigkeit prüfen"]]

class AIResponseSchema(BaseModel):
    warnings: List[ProductWarning]
    description: str = Field(description="Zusammenfassende Beschreibung , wie du den aktuellen Bestand einschätzt, ob gerade viel da ist oder ob bzw. wann ich einkaufen muss, und welche generellen Empfehlungen du hast, die nicht in den Details bereits auftauchen.")

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

class ReceiptItem(BaseModel):
    receipt_name: str = Field(description="Der exakte Text auf dem Kassenzettel (z.B. 'GUT&GÜNSTIG H-MILCH')")
    amount: float = Field(description="Erkannte Menge/Anzahl auf dem Beleg")
    mapped_product_id: int | None = Field(description="Die ID aus dem Grocy-Produktkatalog. Null, wenn das Produkt nicht sicher zugeordnet werden kann.")
    confidence: str = Field(description="Wie sicher ist die Zuordnung? ('hoch', 'mittel', 'gering')")

class ReceiptAnalysisSchema(BaseModel):
    items: List[ReceiptItem]