import asyncio
import json
import os
import re
from typing import Dict, List, Any, Optional

# NOU: Am adăugat Depends și Header pentru securitate
from fastapi import FastAPI, HTTPException, Depends, Header
from pydantic import BaseModel
from supabase import create_client, Client
import google.generativeai as genai
import uvicorn
from dotenv import load_dotenv
import geopy.distance

# --- 1. CONFIGURARE ---
load_dotenv()
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(supabase_url, supabase_key)

try:
    api_key = os.getenv("tudsecret")
    if not api_key:
        raise ValueError("EROARE: Cheia 'tudsecret' nu a fost găsită.")
    genai.configure(api_key=api_key)
except Exception as e:
    raise RuntimeError(f"EROARE: Nu s-a putut inițializa clientul GenAI. Detalii: {e}")

# --- NOU: SECȚIUNEA DE SECURITATE CU CHEIE PRIVATĂ ---
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
    title="Consultant AI Flexibil pentru Planuri de Renovare",
    description="Trimite o cerință și, opțional, o arie geografică pentru a primi planuri strategice."
)

# --- 4. DEFINIREA STRUCTURILOR DE DATE ---
class UserRequest(BaseModel):
    cerinta_user: str
    latitudine: Optional[float] = None
    longitudine: Optional[float] = None
    raza_km: Optional[float] = None

# --- 5. FUNCȚII HELPER ---
# (Toate funcțiile helper: este_in_raza, incarca_toate_locatiile, gaseste_locatii_apropiate
# și generate_renovation_blueprint_with_ai rămân neschimbate)

def este_in_raza(coord_start: tuple, coord_verificare: tuple, raza_km: float) -> tuple[bool, float]:
    distanta_calculata_km = geopy.distance.great_circle(coord_start, coord_verificare).km
    return distanta_calculata_km <= raza_km, distanta_calculata_km

def incarca_toate_locatiile() -> List[Dict]:
    try:
        response = supabase.table('locatii').select('json_locatie').eq('de_folosit', True).execute()
        return [item['json_locatie'] for item in response.data if 'json_locatie' in item]
    except Exception as e:
        print(f"❌ EROARE la încărcarea tuturor locațiilor: {e}")
        return []

def gaseste_locatii_apropiate(coord_start: tuple, raza_km: float) -> List[Dict]:
    print(f"\n--- Se filtrează locațiile pe o rază de {raza_km} km de la {coord_start} ---")
    try:
        response = supabase.rpc('get_locatii_ca_text').execute()
        toate_locatiile = response.data
        locatii_filtrate = []
        for locatie in toate_locatiile:
            geo_string = locatie.get('locatie_geo')
            if not geo_string: continue
            coords = re.findall(r'-?\d+\.\d+', geo_string)
            if len(coords) == 2:
                long_str, lat_str = coords
                locatie_de_verificat = (float(lat_str), float(long_str))
                in_raza, distanta = este_in_raza(coord_start, locatie_de_verificat, raza_km)
                if in_raza:
                    nume_locatie = locatie.get('nume_locatie')
                    print(f"✅ Găsit în rază: '{nume_locatie}' (la {distanta:.2f} km)")
                    full_data_resp = supabase.table('locatii').select('json_locatie').eq('nume_locatie', nume_locatie).single().execute()
                    if full_data_resp.data:
                        locatii_filtrate.append(full_data_resp.data['json_locatie'])
        return locatii_filtrate
    except Exception as e:
        print(f"❌ EROARE la filtrarea locațiilor: {e}")
        return []

async def generate_renovation_blueprint_with_ai(property_data: Dict[str, Any], user_request: str) -> Dict[str, Any]:
    property_context = json.dumps(property_data, indent=2, ensure_ascii=False)
    prompt = f"""
ACȚIONEAZĂ CA UN CONSULTANT SENIOR ÎN INVESTIȚII IMOBILIARE.

CONTEXT:
- Cerința utilizatorului: "{user_request}" (Extrage de aici bugetul maxim disponibil).
- Datele complete ale proprietății de analizat: {property_context}

MISIUNEA TA:
Evaluează fezabilitatea renovării conform bugetului. Generează o analiză complexă în format JSON valid care include verdictul, planul de acțiune și analize suplimentare (financiare, de risc, planificare).

STRUCTURA JSON DE IEȘIRE OBLIGATORIE:
Respectă *strict* următoarea structură arborescentă JSON:

```json
{{
  "analiza_investitie": {{
    "nume_locatie": "string",
    "buget_client_eur": "number",
    "cost_estimat_renovare_eur": "number",
    "verdict": {{
      "status": "string",
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
        response = await model.generate_content_async(prompt, generation_config=genai.types.GenerationConfig(response_mime_type="application/json"))
        return json.loads(response.text)
    except Exception as e:
        return {"analiza_investitie": {"verdict": {"status": "Eroare la Analiza AI", "rezumat": str(e)}}}

# --- 6. ENDPOINT-UL API PRINCIPAL (MODIFICAT PENTRU SECURITATE) ---
@app.post("/planuri-renovare-strategice", response_model=Dict[str, List[Dict]])
async def get_strategic_renovation_plans(request: UserRequest, _=Depends(verify_private_key)):
    """
    Orchestrează procesul. Acest endpoint este acum protejat de o cheie privată.
    """
    locatii_de_analizat = []

    if request.latitudine is not None and request.longitudine is not None and request.raza_km is not None:
        print("MOD DE OPERARE: Filtrare Geografică")
        coord_start = (request.latitudine, request.longitudine)
        locatii_de_analizat = gaseste_locatii_apropiate(coord_start, request.raza_km)
    else:
        print("MOD DE OPERARE: Analiză Totală (fără filtru geo)")
        locatii_de_analizat = incarca_toate_locatiile()
    
    if not locatii_de_analizat:
        return {"rezultate": []}

    tasks = []
    for property_data in locatii_de_analizat:
        tasks.append(generate_renovation_blueprint_with_ai(property_data, request.cerinta_user))

    final_blueprints = await asyncio.gather(*tasks)
    return {"rezultate": final_blueprints}

# --- 7. PORNIREA SERVERULUI ---
if __name__ == "__main__":
    if not PRIVATE_KEY_CORECTA:
        print("⚠️ AVERTISMENT: Cheia 'PRIVATE_ACCESS_KEY' nu este setată în fișierul .env. API-ul nu va fi securizat corespunzător.")
    print("--- Serverul pornește ---")
    print("Accesează documentația API la adresa: http://127.0.0.1:8000/docs")
    uvicorn.run(app, host="127.0.0.1", port=8000)