import asyncio
import json
import os
from typing import Dict, List, Any

# FastAPI și securitate
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Servicii externe
from dotenv import load_dotenv
from supabase import create_client, Client
import google.generativeai as genai
from google.generativeai import types
import uvicorn

# --- 1. CONFIGURARE ȘI INIȚIALIZARE ---
load_dotenv()

# Configurare Supabase
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(supabase_url, supabase_key)

# Configurare Google GenAI
try:
    gemini_api_key = os.getenv("tudsecret")
    if not gemini_api_key:
        raise ValueError("EROARE: Cheia 'tudsecret' pentru Google AI nu a fost găsită în .env.")
    genai.configure(api_key=gemini_api_key)
except Exception as e:
    raise RuntimeError(f"EROARE la inițializarea clientului GenAI: {e}")

# --- 2. SECURITATE CU CHEIE PRIVATĂ ---
PRIVATE_KEY_CORECTA = os.getenv("PRIVATE_ACCESS_KEY")

async def verify_private_key(x_private_key: str | None = Header(None)):
    """Verifică dacă header-ul X-Private-Key conține cheia corectă."""
    if not PRIVATE_KEY_CORECTA:
        raise HTTPException(status_code=500, detail="Cheia privată nu este configurată pe server.")
    if not x_private_key:
        raise HTTPException(status_code=401, detail="Header-ul X-Private-Key lipsește.")
    if x_private_key != PRIVATE_KEY_CORECTA:
        raise HTTPException(status_code=403, detail="Acces neautorizat. Cheia privată este invalidă.")

# --- 3. APLICAȚIA FASTAPI ---
app = FastAPI(
    title="Consultant AI pentru Planuri de Renovare",
    description="API securizat care generează planuri strategice de renovare pe baza unui buget."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class UserRequest(BaseModel):
    cerinta_user: str

# --- 4. LOGICA DE BAZĂ A APLICAȚIEI ---
def load_all_json_data() -> Dict[str, dict]:
    """Încarcă toate locațiile active din Supabase."""
    all_data = {}
    response = supabase.table('locatii').select('json_locatie').eq('de_folosit', True).execute()
    if response.data:
        for item in response.data:
            json_content = item.get('json_locatie', {})
            location_name = json_content.get('nume_locatie')
            if location_name:
                all_data[location_name] = json_content
    return all_data

async def generate_renovation_blueprint_with_ai(property_data: Dict[str, Any], user_request: str) -> Dict[str, Any]:
    """Generează un plan de renovare detaliat folosind AI."""
    property_context = json.dumps(property_data, indent=2, ensure_ascii=False)
    
    prompt = f"""
ACȚIONEAZĂ CA UN CONSULTANT SENIOR ÎN INVESTIȚII IMOBILIARE.

CONTEXT:
- Cerința utilizatorului: "{user_request}"
- Datele proprietății: {property_context}

MISIUNEA TA:
Generează o analiză complexă în format JSON valid, conform structurii obligatorii, care include un scor de investiție de la 0.0 la 100.0, verdict, plan de acțiune și analize financiare, de risc și de planificare.

STRUCTURA JSON DE IEȘIRE OBLIGATORIE:
```json
{{
  "analiza_investitie": {{
    "nume_locatie": "string",
    "scor_investitie": "number",
    "buget_client_eur": "number",
    "cost_estimat_renovare_eur": "number",
    "verdict": {{ ... }},
    "plan_de_actiune": {{ ... }},
    "analiza_financiara": {{ ... }},
    "analiza_de_risc": {{ ... }},
    "planificare_si_etape": {{ ... }}
  }}
}}
"""
    try:
        model = genai.GenerativeModel('gemini-2.5-pro')
        response = await model.generate_content_async(
            prompt,
            generation_config=genai.types.GenerationConfig(
                response_mime_type="application/json",
                temperature=0.2
            )
        )
        return json.loads(response.text)
    except Exception as e:
        # Returnează o eroare structurată în caz de eșec la generare
        return {
            "analiza_investitie": {
                "nume_locatie": property_data.get("nume_locatie", "N/A"),
                "scor_investitie": 0.0,
                "verdict": {
                    "status": "Eroare la Analiza AI",
                    "rezumat": f"A apărut o eroare la generarea planului: {str(e)}",
                    "recomandare_principala": "Verifică setările sau încearcă din nou."
                }
            }
        }

# --- 5. ENDPOINT-UL PRINCIPAL ---
@app.post("/planuri-renovare-strategice", response_model=Dict[str, List[Dict]])
async def get_strategic_renovation_plans(request: UserRequest, _ = Depends(verify_private_key)) -> Dict[str, List[Dict[str, Any]]]:
    """
    Orchestrează întregul proces: încarcă datele, generează planuri pentru toate
    locațiile și returnează rezultatele sortate.
    """
    all_locations_dict = load_all_json_data()
    if not all_locations_dict:
        raise HTTPException(status_code=404, detail="Nicio locație validă nu a fost găsită în baza de date.")

    tasks = [
        generate_renovation_blueprint_with_ai(property_data, request.cerinta_user)
        for property_data in all_locations_dict.values()
    ]

    final_blueprints = await asyncio.gather(*tasks) if tasks else []

    sorted_results = sorted(
        final_blueprints, 
        key=lambda x: x.get("analiza_investitie", {}).get("scor_investitie", 0), 
        reverse=True
    )

    return {"rezultate": sorted_results}

# --- 6. PORNIREA SERVERULUI ---
if __name__ == "__main__":
    print("--- 🚀 Serverul pornește ---")
    print("Accesează documentația API la adresa: http://127.0.0.1:8000/docs")
    uvicorn.run(app, host="127.0.0.1", port=8000)
