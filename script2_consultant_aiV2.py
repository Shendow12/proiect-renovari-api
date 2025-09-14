import asyncio
import json
import os
from typing import Dict, List
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# Import the new library and its types
from google import genai
from google.genai import types

# --- 1. NEW SDK CONFIGURATION ---
load_dotenv()
try:
    # The new SDK automatically finds the GOOGLE_API_KEY from your .env file
    client = genai.Client()
except Exception as e:
    raise RuntimeError(f"EROARE: Nu s-a putut initializa clientul GenAI. Verifica variabila de mediu. Detalii: {e}")

JSON_FOLDER = "Analiza_JSON"

app = FastAPI(
    title="Consultant AI pentru Selecție Renovări",
    description="Trimite un buget și primește analizele JSON complete pentru toate proprietățile potrivite."
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with your specific frontend URL
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# --- 2. MODELUL DE DATE PENTRU REQUEST ---
class UserRequest(BaseModel):
    cerinta_user: str

def load_all_json_data(output_filename: str = "concatenated_results.json") -> Dict[str, dict]:
    """
    Încarcă toate analizele JSON într-un dicționar, le salvează într-un singur
    fișier JSON și returnează dicționarul.
    """
    all_data = {}
    if not os.path.isdir(JSON_FOLDER):
        os.makedirs(JSON_FOLDER, exist_ok=True)
        return {}

    for filename in os.listdir(JSON_FOLDER):
        if filename.endswith(".json") and filename != output_filename:
            location_name = filename.replace(".json", "")
            file_path = os.path.join(JSON_FOLDER, filename)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    ordered_data = {'nume_locatie': location_name, **data}
                    all_data[location_name] = ordered_data
            except Exception:
                continue

    if all_data:
        output_path = os.path.join(JSON_FOLDER, output_filename)
        try:
            data_to_save = list(all_data.values())
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"Eroare la salvarea fișierului concatenat: {e}")

    return all_data

# --- 3. COMPLETELY REWRITTEN AI FUNCTION ---
async def select_matching_locations_with_ai(cerinta_user: str, context_data: str) -> str:
    """
    Face un AI call folosind NOUL SDK pentru a selecta numele TUTUROR locațiilor potrivite.
    """
    # The prompt remains the most powerful tool to get the model to "think".
    prompt = f"""
    Acționează ca un asistent expert în analiză financiară și imobiliară.

    CONTEXT: Ai primit o listă de proprietăți în format JSON. Fiecare are un 'nume_locatie' și un 'cost_estimat_total_eur'.
    ---
    {context_data}
    ---

    CERINȚA UTILIZATORULUI: "{cerinta_user}"

    MISIUNEA TA DETALIATĂ:
    1.  Raționament Inițial: Privește cerința utilizatorului și extrage cu precizie bugetul numeric maxim disponibil pentru renovare. Transforma folosind un curs echitabil daca utilizatorul vorbeste in alta moneda.
    2.  Analiză Comparativă: Pentru fiecare proprietate din context, compară valoarea din 'cost_estimat_total_eur' cu bugetul extras.
    3.  Filtrare Logică: Creează o listă internă cu numele tuturor proprietăților ('nume_locatie') al căror cost este mai mic sau egal cu bugetul.
    4.  Gestionarea Cazului "Niciun Rezultat": Dacă lista ta internă este goală după filtrare, răspunsul tău final trebuie să fie exact textul "N/A".
    5. Daca bugetul acopera mai multe proprietati, selecteaza toate proprietatile care se incadreaza in buget, calculand costul total
    6.  Formatarea Finală: Dacă lista conține una sau mai multe proprietăți, combină numele acestora într-un singur string, separate strict prin virgulă, FĂRĂ spații sau alte caractere. Nu adăuga nicio explicație sau introducere.

    Exemplu de răspuns valid pentru o selecție reușită:
    Locatie2,Locatie4,Locatie7
    """
    

    try:
        # The new SDK uses a 'config' object passed directly to the method.
        config = types.GenerateContentConfig(
            max_output_tokens=81920,
            temperature=0.0,
            thinking_config=types.ThinkingConfig(thinking_budget=-1, include_thoughts=True)

            
        )

        # The new async call structure: client.aio.models.generate_content
        response = await client.aio.models.generate_content(
            model='gemini-2.5-pro',  # Using a modern model name
            contents=prompt,
            config=config
        )
        
        
        # --- NEW LOGIC BASED ON THE DOCUMENTATION ---
        final_answer_parts = []
        print("\n--- 🧠 AI's Interleaved Thoughts & Answer ---")

        for part in response.candidates[0].content.parts:
            # Check if the part is a "thought"
            if hasattr(part, 'thought') and part.thought:
                print(f"\n[THOUGHT]:\n{part.text}")
            # Otherwise, it's part of the final answer
            else:
                final_answer_parts.append(part.text)
        
        print("------------------------------------------\n")

        # Join the collected answer parts to form the final response
        final_answer = "".join(final_answer_parts)
        return final_answer.strip()
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"A apărut o eroare la selecția AI: {e}")


# --- 4. ENDPOINT-UL API (No changes needed here) ---
@app.post("/recomandari-multiple-json", response_model=Dict[str, List[dict]])
async def get_json_recommendations_endpoint(request: UserRequest):
    """
    Primește cerința utilizatorului și returnează o listă cu analizele JSON complete
    pentru TOATE proprietățile potrivite, selectate de AI.
    """
    all_locations_dict = load_all_json_data()
    if not all_locations_dict:
        raise HTTPException(status_code=404, detail="Nicio analiză JSON nu a fost găsită.")

    context_for_ai = json.dumps(list(all_locations_dict.values()), indent=2, ensure_ascii=False)
    
    selected_locations_string = await select_matching_locations_with_ai(
        cerinta_user=request.cerinta_user,
        context_data=context_for_ai
    )
    
    if not selected_locations_string or selected_locations_string == "N/A":
        return {"rezultate": []} # Returneaza o lista goala pentru consistenta

    location_names_list = [name.strip() for name in selected_locations_string.split(',')]
    
    matching_jsons = []
    for name in location_names_list:
        if name in all_locations_dict:
            matching_jsons.append(all_locations_dict[name])
            
    sorted_results = sorted(matching_jsons, key=lambda x: x.get("cost_estimat_total_eur", 0))

    return {"rezultate": sorted_results}