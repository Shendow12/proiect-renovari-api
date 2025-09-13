import google.generativeai as genai
import os
from PIL import Image
import json
from tqdm import tqdm

# --- CONFIGURARE ---
# 1. Obține cheia API de la Google AI Studio: https://aistudio.google.com/app/apikey
# 2. Setează cheia ca variabilă de mediu numită "GOOGLE_API_KEY"
#    sau adaug-o direct aici (nerecomandat pentru siguranță):
#    GOOGLE_API_KEY = "CHEIA_TA_API_AICI"
try:
    genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
except KeyError:
    print("EROARE: Variabila de mediu GOOGLE_API_KEY nu este setată.")
    print("Te rog configurează cheia API conform instrucțiunilor din cod.")
    exit()

# --- DEFINIREA FOLDERELOR ---
INPUT_FOLDER = "Locatii_de_Analizat"
OUTPUT_FOLDER = "Analiza_JSON"

# Crearea folderului de output dacă nu există
os.makedirs(OUTPUT_FOLDER, exist_ok=True)


def analyze_location(location_folder_path):
    """
    Analizează toate imaginile dintr-un folder și returnează un JSON cu costurile de renovare.
    """
    image_parts = []
    location_name = os.path.basename(location_folder_path)
    
    # Încarcă toate imaginile din folder
    print(f"\nProcesare locație: {location_name}")
    image_files = [f for f in os.listdir(location_folder_path) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))]
    
    if not image_files:
        print(f"AVERTISMENT: Nu am găsit imagini în folderul {location_name}. Sar peste.")
        return None

    for image_file in image_files:
        try:
            img_path = os.path.join(location_folder_path, image_file)
            img = Image.open(img_path)
            image_parts.append(img)
        except Exception as e:
            print(f" AVERTISMENT: Nu am putut încărca imaginea {image_file}. Eroare: {e}")

    # Definirea modelului și a prompt-ului
    model = genai.GenerativeModel('gemini-2.5-flash')
    
    prompt_text = """
    Analizează următoarele imagini ale unei proprietăți imobiliare din România. Acționează ca un expert în renovări.
    Obiectivul tău este să identifici TOATE elementele care necesită renovare, reparație sau înlocuire pentru a aduce proprietatea la un standard modern, potrivit pentru închiriere.

    Pentru analiză, te rog să:
    1.  Identifici fiecare element specific care necesită atenție (ex: 'Parchet sufragerie', 'Gresie baie', 'Ferestre dormitor', 'Uși interioare', 'Instalație electrică vizibilă').
    2.  Pentru fiecare element, descrie pe scurt starea lui (ex: 'zgâriat și umflat', 'model vechi, crăpată', 'din lemn, vopsea scorojită').
    3.  Estimează un cost realist în EURO pentru reparația sau înlocuirea fiecărui element, incluzând manopera, bazându-te pe cunoștințele tale despre piața din România.
    4.  Calculează un cost total estimat pentru renovare.
    5.  Oferă un scurt rezumat al analizei și o părere despre potențialul proprietății.

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
        # Generarea răspunsului de la AI
        print(" Se trimit imaginile către AI pentru analiză... (acest pas poate dura)")
        response = model.generate_content([prompt_text] + image_parts)
        
        # Curățarea și parsarea răspunsului JSON
        cleaned_response = response.text.strip().replace("```json", "").replace("```", "")
        analysis_json = json.loads(cleaned_response)
        
        return analysis_json

    except Exception as e:
        print(f" EROARE la analiza AI pentru {location_name}: {e}")
        return None

# --- EXECUȚIA PRINCIPALĂ ---
if __name__ == "__main__":
    if not os.path.isdir(INPUT_FOLDER):
        print(f"EROARE: Folderul de intrare '{INPUT_FOLDER}' nu există. Te rog creează-l și adaugă foldere cu locații.")
    else:
        location_folders = [d for d in os.listdir(INPUT_FOLDER) if os.path.isdir(os.path.join(INPUT_FOLDER, d))]
        
        print(f"Am găsit {len(location_folders)} locații de analizat.")
        
        for location_name in tqdm(location_folders, desc="Progres total analiză"):
            location_path = os.path.join(INPUT_FOLDER, location_name)
            
            # Verificăm dacă analiza există deja pentru a nu re-procesa
            output_file_path = os.path.join(OUTPUT_FOLDER, f"{location_name}.json")
            if os.path.exists(output_file_path):
                print(f"\nAnaliza pentru {location_name} există deja. Sar peste.")
                continue

            # Rulăm analiza
            result = analyze_location(location_path)
            
            # Salvăm rezultatul
            if result:
                with open(output_file_path, 'w', encoding='utf-8') as f:
                    json.dump(result, f, indent=2, ensure_ascii=False)
                print(f" Analiza pentru {location_name} a fost salvată cu succes!")

        print("\nAnaliză finalizată pentru toate locațiile!")