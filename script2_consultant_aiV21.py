import asyncio
import json
import os
from typing import Dict, List, Any
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# Importă bibliotecile Google GenAI și Uvicorn
import google.generativeai as genai
from google.generativeai import types
import uvicorn

# --- 1. CONFIGURARE SDK ---
load_dotenv()
try:
    # Preia cheia API din fișierul .env sau variabilele de mediu
    api_key = os.getenv("tudsecret")
    
    if not api_key:
        raise ValueError("EROARE: Cheia 'tudsecret' nu a fost găsită în fișierul .env.")
    
    genai.configure(api_key=api_key)

except Exception as e:
    raise RuntimeError(f"EROARE: Nu s-a putut inițializa clientul GenAI. Detalii: {e}")

JSON_FOLDER = "Analiza_JSON"

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
    """Încarcă toate fișierele JSON dintr-un folder specificat."""
    all_data = {}
    if not os.path.isdir(JSON_FOLDER):
        os.makedirs(JSON_FOLDER, exist_ok=True)
        return {}
    for filename in os.listdir(JSON_FOLDER):
        if filename.endswith(".json"):
            location_name = filename.replace(".json", "")
            file_path = os.path.join(JSON_FOLDER, filename)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    data['nume_locatie'] = location_name 
                    all_data[location_name] = data
            except Exception:
                continue
    return all_data
    
# --- 2. FUNCȚIA DE FILTRARE A FOST ELIMINATĂ ---
# async def select_matching_locations_with_ai(...): -> NU MAI EXISTĂ

# --- 3. FUNCȚIA AI PENTRU GENERAREA PLANULUI STRATEGIC (Analizorul Detaliat) ---
async def generate_renovation_blueprint_with_ai(property_data: Dict[str, Any], user_request: str) -> Dict[str, Any]:
    """
    Pentru o singură proprietate, generează un plan strategic de renovare (blueprint) extins,
    incluzând analiză financiară, de risc și de planificare.
    """
    property_context = json.dumps(property_data, indent=2, ensure_ascii=False)
    
    prompt = f"""
    ACȚIONEAZĂ CA UN CONSULTANT SENIOR ÎN INVESTIȚII IMOBILIARE.

    CONTEXT:
    - Cerința utilizatorului: "{user_request}" (Extrage de aici bugetul maxim disponibil).
    - Datele complete ale proprietății de analizat: {property_context}

    MISIUNEA TA:
    Evaluează fezabilitatea renovării conform bugetului. Generează o analiză complexă în format JSON valid care include verdictul, planul de acțiune și analize suplimentare (financiare, de risc, planificare).

    GHID DE RAȚIONAMENT:
    1.  **Renovare Completă:** Dacă bugetul >= `cost_estimat_total_eur`. Toate elementele merg în `plan_de_actiune`.
    2.  **Renovare Parțială:** Dacă bugetul < `cost_estimat_total_eur` DAR bugetul >= costul total al elementelor cu prioritate 'Critic'. Pune elementele care nu se încadrează în buget în `elemente_amanate`.
    3.  **Proiect Nefezabil (Respins):** Dacă bugetul < costul total al elementelor cu prioritate 'Critic'. `plan_de_actiune` este gol.
    """
    try:
        # **CORECTAT** Numele modelului la 'gemini-1.5-pro-latest'
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
        return {
            "nume_locatie": property_data.get("nume_locatie", "N/A"),
            "verdict_strategic": "Eroare la Analiza",
            "scor_investitie": 0.0,
            "rezumat": f"A apărut o eroare în timpul generării planului: {str(e)}",
        }

# --- 4. MODIFICAT: ENDPOINT-UL API CARE ORCHESTREAZĂ TOTUL FĂRĂ FILTRU ---
@app.post("/planuri-renovare-strategice", response_model=Dict[str, List[Dict]])
async def get_strategic_renovation_plans(request: UserRequest):
    """
    Orchestrează întregul proces: încarcă datele, generează planuri detaliate pentru TOATE 
    locațiile în paralel cu pauză și returnează rezultatele.
    """
    all_locations_dict = load_all_json_data()
    if not all_locations_dict:
        raise HTTPException(status_code=404, detail="Nicio analiză JSON nu a fost găsită în folderul 'Analiza_JSON'.")

    # Pas 1: Preia numele tuturor locațiilor direct din datele încărcate
    location_names_list = list(all_locations_dict.keys())
    
    # Pas 2: Crearea task-urilor pentru toate locațiile
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

    # Pas 3: Așteptarea finalizării tuturor task-urilor
    print("--- 🏁 Toate task-urile au fost lansate. Se așteaptă finalizarea... ---")
    if tasks:
        final_blueprints = await asyncio.gather(*tasks)
    else:
        final_blueprints = []

    # Sortarea finală a rezultatelor după scorul de investiție
    sorted_results = sorted(final_blueprints, key=lambda x: x.get("scor_investitie", 0), reverse=True)

    return {"rezultate": sorted_results}

# --- 5. PORNIREA SERVERULUI ---
if __name__ == "__main__":
    print("--- Serverul pornește ---")
    print("Accesează documentația API la adresa: http://127.0.0.1:8000/docs")
    uvicorn.run(app, host="127.0.0.1", port=8000)