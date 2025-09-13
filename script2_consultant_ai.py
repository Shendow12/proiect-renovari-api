import json
import asyncio
import google.generativeai as genai
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
from typing import Dict, List

# --- 1. CONFIGURARE ---
try:
    genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
except KeyError:
    raise RuntimeError("EROARE: Variabila de mediu 'GOOGLE_API_KEY' nu este setată.")

JSON_FOLDER = "Analiza_JSON"

app = FastAPI(
    title="Consultant AI pentru Selecție Renovări",
    description="Trimite un buget și primește analizele JSON complete pentru toate proprietățile potrivite."
)

# --- 2. MODELUL DE DATE PENTRU REQUEST ---
class UserRequest(BaseModel):
    cerinta_user: str

# --- 3. LOGICA DE BAZĂ ---
def load_all_json_data() -> Dict[str, dict]:
    """Încarcă toate analizele JSON într-un dicționar pentru acces rapid."""
    all_data = {}
    if not os.path.isdir(JSON_FOLDER):
        return {}

    for filename in os.listdir(JSON_FOLDER):
        if filename.endswith(".json"):
            location_name = filename.replace(".json", "")
            file_path = os.path.join(JSON_FOLDER, filename)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Creăm un nou dicționar cu 'nume_locatie' la început
                    ordered_data = {'nume_locatie': location_name, **data}
                    all_data[location_name] = ordered_data
            except Exception:
                continue
    return all_data

async def select_matching_locations_with_ai(cerinta_user: str, context_data: str) -> str:
    """
    Face un AI call pentru a selecta numele TUTUROR locațiilor potrivite.
    """
    prompt = f"""
    Acționează ca un asistent inteligent care filtrează o listă de opțiuni.

    CONTEXT: Mai jos este o listă de proprietăți analizate, în format JSON. Fiecare proprietate are un 'nume_locatie' și un 'cost_estimat_total_eur' pentru renovare.
    ---
    {context_data}
    ---

    CERINȚA UTILIZATORULUI: "{cerinta_user}"

    MISIUNEA TA:
    1. Analizează cerința utilizatorului pentru a înțelege bugetul disponibil PENTRU RENOVARE.
    2. Compară bugetul utilizatorului cu câmpul 'cost_estimat_total_eur' pentru fiecare proprietate din context.
    3. Identifică TOATE proprietățile care se încadrează în buget (cost <= buget).
    4. Dacă nicio proprietate nu se încadrează, returnează textul "N/A".
    5. Returnează DOAR și STRICT o listă cu 'nume_locatie' pentru fiecare proprietate potrivită, separate prin virgulă, FĂRĂ SPAȚII.

    Exemplu de răspuns valid:
    Locatie2,Locatie4,Locatie7
    """
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = await model.generate_content_async(prompt)
        return response.text.strip()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"A apărut o eroare la selecția AI: {e}")

# --- 4. ENDPOINT-UL API ---
@app.post("/recomandari-multiple-json", response_model=Dict[str, List[dict]])
async def get_json_recommendations_endpoint(request: UserRequest):
    """
    Primește cerința utilizatorului și returnează o listă cu analizele JSON complete
    pentru TOATE proprietățile potrivite, selectate de AI.
    """
    # Pas 1: Încarcă datele din fișierele JSON
    all_locations_dict = load_all_json_data()
    if not all_locations_dict:
        raise HTTPException(status_code=404, detail="Nicio analiză JSON nu a fost găsită.")

    context_for_ai = json.dumps(list(all_locations_dict.values()), indent=2, ensure_ascii=False)
    
    # Pas 2: Obține numele locațiilor selectate de la AI (string separat prin virgulă)
    selected_locations_string = await select_matching_locations_with_ai(
        cerinta_user=request.cerinta_user,
        context_data=context_for_ai
    )
    
    # Pas 3: Procesează răspunsul și construiește lista finală de JSON-uri
    if selected_locations_string == "N/A":
        return {"rezultate": []}

    # Transformă string-ul "Locatie1,Locatie2" în lista ["Locatie1", "Locatie2"]
    location_names_list = selected_locations_string.split(',')
    
    matching_jsons = []
    for name in location_names_list:
        if name in all_locations_dict:
            matching_jsons.append(all_locations_dict[name])
            
    # Sortează rezultatele final de la cel mai ieftin la cel mai scump
    sorted_results = sorted(matching_jsons, key=lambda x: x.get("cost_estimat_total_eur", 0))

    return {"rezultate": sorted_results}

