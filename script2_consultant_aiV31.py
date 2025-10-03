import asyncio
import json
import os
import re
from typing import Dict, List, Any, Optional

# FastAPI, Pydantic și Securitate
from fastapi import FastAPI, HTTPException, Depends, Header
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware


# Servicii externe
from supabase import create_client, Client
import google.generativeai as genai
import uvicorn
from dotenv import load_dotenv
import geopy.distance

# --- 1. CONFIGURARE ---
load_dotenv()

# Configurare Supabase
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(supabase_url, supabase_key)

# Configurare Google GenAI
try:
    api_key = os.getenv("tudsecret")
    if not api_key:
        raise ValueError("EROARE: Cheia 'tudsecret' nu a fost găsită în .env.")
    genai.configure(api_key=api_key)
except Exception as e:
    raise RuntimeError(f"EROARE la inițializarea clientului GenAI: {e}")

# Configurare Cheie Privată pentru API
PRIVATE_KEY_CORECTA = os.getenv("PRIVATE_ACCESS_KEY")

# --- 2. SECURITATE ---
async def verify_private_key(x_private_key: str | None = Header(None)):
    """Verifică dacă header-ul X-Private-Key este prezent și corect."""
    if not PRIVATE_KEY_CORECTA:
        raise HTTPException(status_code=500, detail="Cheia privată a API-ului nu este configurată pe server.")
    if not x_private_key:
        raise HTTPException(status_code=401, detail="Header-ul X-Private-Key lipsește din request.")
    if x_private_key != PRIVATE_KEY_CORECTA:
        raise HTTPException(status_code=403, detail="Acces neautorizat. Cheia privată este invalidă.")

# --- 3. APLICAȚIA FASTAPI ---
app = FastAPI(
    title="Consultant AI Flexibil pentru Planuri de Renovare",
    description="API securizat care generează planuri strategice de renovare."
)

# Adăugarea middleware-ului CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Pentru producție, înlocuiește cu domeniul front-end-ului
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 4. STRUCTURI DE DATE (Pydantic Models) ---
class UserRequest(BaseModel):
    cerinta_user: str
    latitudine: Optional[float] = None
    longitudine: Optional[float] = None
    raza_km: Optional[float] = None

# --- 5. FUNCȚII HELPER ---

def este_in_raza(coord_start: tuple, coord_verificare: tuple, raza_km: float) -> tuple[bool, float]:
    """Calculează distanța și returnează (True/False, distanța)."""
    distanta_km = geopy.distance.great_circle(coord_start, coord_verificare).km
    return distanta_km <= raza_km, distanta_km

def incarca_toate_locatiile() -> List[Dict]:
    """Încarcă numele și analiza JSON pentru toate locațiile active."""
    try:
        response = supabase.table('locatii').select('nume_locatie, json_locatie').eq('de_folosit', True).execute()
        return response.data
    except Exception as e:
        print(f"❌ EROARE la încărcarea tuturor locațiilor: {e}")
        return []

def gaseste_locatii_apropiate(coord_start: tuple, raza_km: float) -> List[Dict]:
    """Filtrează locațiile și returnează o listă de dicționare (nume + json_locatie)."""
    print(f"\n--- Se filtrează locațiile pe o rază de {raza_km} km de la {coord_start} ---")
    try:
        response = supabase.rpc('get_locatii_ca_text').execute()
        toate_locatiile_geo = response.data
        
        locatii_filtrate_final = []
        for locatie_geo in toate_locatiile_geo:
            geo_string = locatie_geo.get('locatie_geo')
            if not geo_string: continue

            coords = re.findall(r'-?\d+\.\d+', geo_string)
            if len(coords) == 2:
                long_str, lat_str = coords
                locatie_de_verificat = (float(lat_str), float(long_str))
                
                in_raza, distanta = este_in_raza(coord_start, locatie_de_verificat, raza_km)
                if in_raza:
                    nume_locatie = locatie_geo.get('nume_locatie')
                    print(f"✅ Găsit în rază: '{nume_locatie}' (la {distanta:.2f} km)")
                    
                    full_data_resp = supabase.table('locatii').select('nume_locatie, json_locatie').eq('nume_locatie', nume_locatie).single().execute()
                    if full_data_resp.data:
                        locatii_filtrate_final.append(full_data_resp.data)
        
        return locatii_filtrate_final
    except Exception as e:
        print(f"❌ EROARE la filtrarea locațiilor: {e}")
        return []

async def generate_renovation_blueprint_with_ai(property_data: Dict[str, Any], user_request: str) -> Dict[str, Any]:
    """Generează un plan de renovare detaliat folosind AI."""
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
        model = genai.GenerativeModel('gemini-2.5-pro')
        response = await model.generate_content_async(
            prompt,
            generation_config=genai.types.GenerationConfig(
                response_mime_type="application/json"
            )
        )
        return json.loads(response.text)
    except Exception as e:
        return {"analiza_investitie": {"verdict": {"status": "Eroare la Analiza AI", "rezumat": str(e)}}}

# --- 6. ENDPOINT-UL API PRINCIPAL ---
@app.post("/planuri-renovare-strategice", response_model=Dict[str, List[Dict]])
async def get_strategic_renovation_plans(request: UserRequest, _=Depends(verify_private_key)):
    """
    Orchestrează procesul: filtrează (opțional) și analizează locațiile.
    Acest endpoint este protejat de o cheie privată.
    """
    locatii_de_procesat = []

    if request.latitudine is not None and request.longitudine is not None and request.raza_km is not None:
        print("MOD DE OPERARE: Filtrare Geografică")
        coord_start = (request.latitudine, request.longitudine)
        locatii_de_procesat = gaseste_locatii_apropiate(coord_start, request.raza_km)
    else:
        print("MOD DE OPERARE: Analiză Totală (fără filtru geo)")
        locatii_de_procesat = incarca_toate_locatiile()
    
    if not locatii_de_procesat:
        return {"rezultate": []}

    tasks = []
    print(f"\n--- 🚀 Se pregătesc cererile AI pentru {len(locatii_de_procesat)} locații ---")
    
    for locatie_data in locatii_de_procesat:
        nume_corect = locatie_data.get('nume_locatie')
        analiza_json = locatie_data.get('json_locatie')

        if not nume_corect or not analiza_json:
            continue
        
        # Injectarea numelui corect în JSON-ul de analiză
        if 'nume_locatie' in analiza_json:
            analiza_json['nume_locatie'] = nume_corect
        if 'analiza_investitie' in analiza_json and 'nume_locatie' in analiza_json['analiza_investitie']:
            analiza_json['analiza_investitie']['nume_locatie'] = nume_corect
            
        print(f"  -> Se pregătește task pentru '{nume_corect}'")
        tasks.append(generate_renovation_blueprint_with_ai(analiza_json, request.cerinta_user))

    print("--- 🏁 Se așteaptă finalizarea analizelor AI... ---")
    final_blueprints = await asyncio.gather(*tasks)
    return {"rezultate": final_blueprints}

# --- 7. PORNIREA SERVERULUI ---
if __name__ == "__main__":
    if not PRIVATE_KEY_CORECTA:
        print("⚠️ AVERTISMENT: Cheia 'PRIVATE_ACCESS_KEY' nu este setată în .env. API-ul nu va fi securizat corespunzător.")
    
    print("--- Serverul pornește ---")
    print("Accesează documentația API la adresa: http://127.0.0.1:8000/docs")
    uvicorn.run(app, host="127.0.0.1", port=8000)