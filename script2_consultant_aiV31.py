import asyncio
import json
import os
from typing import Dict, List, Any
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from supabase import create_client, Client
import google.generativeai as genai
from google.generativeai import types
import uvicorn

# --- 1. CONFIGURARE SDK ---
load_dotenv()

supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(supabase_url, supabase_key)

try:
    api_key = os.getenv("tudsecret")
    if not api_key:
        raise ValueError("EROARE: Cheia 'tudsecret' nu a fost găsită în fișierul .env.")
    
    genai.configure(api_key=api_key)

except Exception as e:
    raise RuntimeError(f"EROARE: Nu s-a putut inițializa clientul GenAI. Detalii: {e}")

app = FastAPI(
    title="Consultant AI pentru Planuri de Renovare",
    description="Trimite un buget și primește planuri strategice de renovare (blueprints) pentru proprietățile potrivite."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

class UserRequest(BaseModel):
    cerinta_user: str

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
    """
    Pentru o singură proprietate, generează un plan strategic de renovare (blueprint) extins,
    incluzând analiză financiară, de risc, de planificare și un scor de investiție.
    """
    property_context = json.dumps(property_data, indent=2, ensure_ascii=False)
    
    prompt = f"""
ACȚIONEAZĂ CA UN CONSULTANT SENIOR ÎN INVESTIȚII IMOBILIARE.

CONTEXT:
- Cerința utilizatorului: "{user_request}" (Extrage de aici bugetul maxim disponibil).
- Datele complete ale proprietății de analizat: {property_context}

MISIUNEA TA:
Evaluează fezabilitatea renovării conform bugetului. Generează o analiză complexă în format JSON valid.
Pe lângă planul de acțiune și analizele detaliate, calculează un "scor_investitie" de la 0.0 la 100.0, unde 100.0 reprezintă o potrivire perfectă între buget, starea proprietății și potențialul de profit. Un scor mic indică o investiție nepotrivită sau riscantă.

STRUCTURA JSON DE IEȘIRE OBLIGATORIE:
Respectă *strict* următoarea structură arborescentă JSON:

```json
{{
  "analiza_investitie": {{
    "nume_locatie": "string",
    "scor_investitie": "number",
    "buget_client_eur": "number",
    "cost_estimat_renovare_eur": "number",
    "verdict": {{
      "status": "string (Potrivit/Nepotrivit/Necesită Atenție)",
      "rezumat": "string",
      "recomandare_principala": "string"
    }},
    "plan_de_actiune": {{
      "tip_plan": "string",
      "elemente_de_executat": [
        {{
          "element": "string",
          "stare": "string",
          "cost_estimat_element_eur": "number",
          "prioritate": "string (Critic/Major/Mediu)"
        }}
      ],
      "elemente_amanate": [
        {{
          "element": "string",
          "stare": "string",
          "cost_estimat_element_eur": "number",
          "prioritate": "string (Critic/Major/Mediu)"
        }}
      ]
    }},
    "analiza_financiara": {{
      "cost_estimat_total_eur": "number",
      "buget_disponibil_eur": "number",
      "fond_de_rezerva_recomandat_procent": "number",
      "fond_de_rezerva_recomandat_eur": "number",
      "cost_total_proiectat_eur": "number",
      "surplus_bugetar_estimat_eur": "number",
      "observatii_financiare": "string"
    }},
    "analiza_de_risc": {{
      "nivel_risc_general": "string (Scăzut/Mediu/Ridicat)",
      "riscuri_identificate": [
        {{
          "risc": "string",
          "descriere": "string",
          "mitigare": "string"
        }}
      ]
    }},
    "planificare_si_etape": {{
      "durata_estimata_saptamani": "string",
      "etape_recomandate": [
        {{
          "etapa": "number",
          "nume": "string",
          "descriere": "string"
        }}
      ]
    }}
  }}
}}
"""
    try:
        model = genai.GenerativeModel('gemini-1.5-pro-latest')
        response = await model.generate_content_async(
            prompt,
            generation_config=genai.types.GenerationConfig(
                response_mime_type="application/json",
                temperature=0.2
            )
        )
        return json.loads(response.text)
    except Exception as e:
        return {
            "analiza_investitie": {
                "nume_locatie": property_data.get("nume_locatie", "N/A"),
                "scor_investitie": 0.0,
                "buget_client_eur": 0,
                "cost_estimat_renovare_eur": 0,
                "verdict": {
                    "status": "Eroare la Analiza",
                    "rezumat": f"A apărut o eroare tehnică în timpul generării planului: {str(e)}",
                    "recomandare_principala": "Verifică consola serverului pentru detalii sau încearcă din nou."
                },
                "plan_de_actiune": {"tip_plan": "N/A", "elemente_de_executat": [], "elemente_amanate": []},
                "analiza_financiara": {"observatii_financiare": "N/A"},
                "analiza_de_risc": {"nivel_risc_general": "N/A", "riscuri_identificate": []},
                "planificare_si_etape": {"durata_estimata_saptamani": "N/A", "etape_recomandate": []}
            }
        }

@app.post("/planuri-renovare-strategice", response_model=Dict[str, List[Dict]])
async def get_strategic_renovation_plans(request: UserRequest):
    """
    Orchestrează întregul proces: încarcă datele, generează planuri detaliate pentru TOATE
    locațiile în paralel și returnează rezultatele sortate.
    """
    all_locations_dict = load_all_json_data()
    if not all_locations_dict:
        raise HTTPException(status_code=404, detail="Nicio locație validă nu a fost găsită în baza de date.")

    location_names_list = list(all_locations_dict.keys())

    tasks = []
    delay_between_launches_seconds = 1

    print(f"--- 🚀 Se pregătesc cererile pentru TOATE cele {len(location_names_list)} locații ---")
    for name in location_names_list:
        if name in all_locations_dict:
            property_data = all_locations_dict[name]
            task = asyncio.create_task(
                generate_renovation_blueprint_with_ai(property_data, request.cerinta_user)
            )
            tasks.append(task)
            print(f"   -> Task pentru '{name}' a fost lansat.")
            await asyncio.sleep(delay_between_launches_seconds)

    print("--- 🏁 Toate task-urile au fost lansate. Se așteaptă finalizarea... ---")
    if tasks:
        final_blueprints = await asyncio.gather(*tasks)
    else:
        final_blueprints = []

    sorted_results = sorted(
        final_blueprints, 
        key=lambda x: x.get("analiza_investitie", {}).get("scor_investitie", 0), 
        reverse=True
    )

    return {"rezultate": sorted_results}

if __name__ == "__main__":
    print("--- Serverul pornește ---")
    print("Accesează documentația API la adresa: http://127.0.0.1:8000/docs")
    uvicorn.run(app, host="127.0.0.1", port=8000)
