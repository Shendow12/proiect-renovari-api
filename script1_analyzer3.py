import google.generativeai as genai
import os
from PIL import Image
import json
from tqdm import tqdm
from dotenv import load_dotenv
from supabase import create_client, Client

# --- 1. CONFIGURARE ȘI CONECTARE ---
load_dotenv()

# Conectare la Supabase
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
if not url or not key:
    print("❌ EROARE: Asigură-te că ai setat SUPABASE_URL și SUPABASE_KEY în fișierul .env")
    exit()
supabase: Client = create_client(url, key)
print("🔗 Conectat la Supabase cu succes!")

# Configurare Google AI
try:
    genai.configure(api_key=os.environ["tudsecret"])
except KeyError:
    print("❌ EROARE: Variabila de mediu 'tudsecret' pentru cheia Google API nu este setată.")
    exit()

# --- 2. DEFINIREA FUNCȚIILOR ---
INPUT_FOLDER = "Locatii_de_Analizat"

def analyze_location(location_folder_path):
    """
    Analizează toate imaginile dintr-un folder și returnează un JSON cu costurile de renovare.
    """
    image_parts = []
    folder_name = os.path.basename(location_folder_path)
    
    print(f"\n🔍 Procesare imagini pentru: {folder_name}")
    image_files = [f for f in os.listdir(location_folder_path) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))]
    
    if not image_files:
        print(f"⚠️ AVERTISMENT: Nu am găsit imagini în folderul {folder_name}. Sar peste analiza AI.")
        return None

    for image_file in image_files:
        try:
            img_path = os.path.join(location_folder_path, image_file)
            img = Image.open(img_path)
            image_parts.append(img)
        except Exception as e:
            print(f" AVERTISMENT: Nu am putut încărca imaginea {image_file}. Eroare: {e}")

    model = genai.GenerativeModel('gemini-2.5-pro')
    
    prompt_text = """
    Analizează următoarele imagini ale unei proprietăți imobiliare din România. Acționează ca un expert în renovări.
    Obiectivul tău este să identifici TOATE elementele care necesită renovare, reparație sau înlocuire pentru a aduce proprietatea la un standard modern, potrivit pentru închiriere.
    Returnează răspunsul STRICT în format JSON, fără niciun alt text înainte sau după. Structura JSON trebuie să fie următoarea:
    {
      "cost_estimat_total_eur": <număr>,
      "potential_general": "<string>",
      "elemente_identificate": [
        {
          "element": "<string>",
          "stare": "<string>",
          "cost_estimat_element_eur": <număr>
        }
      ],
      "rezumat_analiza": "<string>"
    }
    """
    
    try:
        print("🤖 Se trimit imaginile către AI pentru analiză... (acest pas poate dura)")
        response = model.generate_content([prompt_text] + image_parts)
        
        cleaned_response = response.text.strip().replace("```json", "").replace("```", "")
        analysis_json = json.loads(cleaned_response)
        return analysis_json

    except Exception as e:
        print(f"❌ EROARE la analiza AI pentru {folder_name}: {e}")
        return None

# --- 3. EXECUȚIA PRINCIPALĂ ---
if __name__ == "__main__":
    if not os.path.isdir(INPUT_FOLDER):
        print(f"❌ EROARE: Folderul de intrare '{INPUT_FOLDER}' nu există.")
    else:
        location_folders = [d for d in os.listdir(INPUT_FOLDER) if os.path.isdir(os.path.join(INPUT_FOLDER, d))]
        
        print(f"Am găsit {len(location_folders)} locații de procesat.")
        
        for folder_name in tqdm(location_folders, desc="Progres total"):
            location_path = os.path.join(INPUT_FOLDER, folder_name)
            
            info_locatie = {}
            try:
                with open(os.path.join(location_path, 'info.json'), 'r', encoding='utf-8') as f:
                    info_locatie = json.load(f)
            except FileNotFoundError:
                print(f"\n⚠️ AVERTISMENT: Nu am găsit 'info.json' în folderul '{folder_name}'. Se sare peste acest folder.")
                continue
            except json.JSONDecodeError:
                print(f"\n❌ EROARE: Fișierul 'info.json' din folderul '{folder_name}' este invalid. Se sare peste.")
                continue

            adresa = info_locatie.get("adresa", folder_name)
            
            # --- AICI ESTE MODIFICAREA ---
            lat = info_locatie.get("latitudine")  # Modificat din "lat"
            long = info_locatie.get("longitudine") # Modificat din "long"
            # ---------------------------
            
            response = supabase.table('locatii').select('id', count='exact').eq('nume_locatie', adresa).execute()
            if response.count > 0:
                print(f"\n✅ Locația '{adresa}' există deja în baza de date. Se sare peste.")
                continue

            result_json = analyze_location(location_path)
            
            if result_json:
                try:
                    data_to_insert = {
                        "json_locatie": result_json,
                        "nume_locatie": adresa,
                        "de_folosit": True
                    }
                    
                    if lat is not None and long is not None:
                        data_to_insert['locatie_geo'] = f'POINT({long} {lat})'
                        print(f"📍 Coordonate încărcate pentru {adresa}")
                    else:
                        print(f"⚠️ AVERTISMENT: Coordonate lipsă în 'info.json' pentru '{folder_name}'.")

                    supabase.table('locatii').insert(data_to_insert).execute()
                    print(f"💾 Analiza pentru '{adresa}' a fost salvată cu succes în Supabase!")
                except Exception as e:
                    print(f"❌ EROARE la salvarea în Supabase pentru {adresa}: {e}")

        print("\n🎉 Analiză finalizată pentru toate locațiile!")