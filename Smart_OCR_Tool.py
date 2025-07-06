import os
import re
import easyocr
import math
from PIL import Image
import numpy as np

### --- PART 1: CONFIGURATION --- ###
print("Initializing EasyOCR... (This may take a moment on the first run)")
reader = easyocr.Reader(['en'], gpu=False)
print("EasyOCR Initialized.")

CROP_TOP_PERCENT = 0.15 
CROP_BOTTOM_PERCENT = 0.20 

### --- PART 2: THE FINAL HYBRID LOGIC --- ###

def get_center(bbox):
    return ((bbox[0][0] + bbox[1][0]) / 2, (bbox[0][1] + bbox[2][1]) / 2)

def find_text_below(anchor_location, all_results):
    min_dist = float('inf')
    found_text = None
    for (bbox, text, prob) in all_results:
        text_center = get_center(bbox)
        if text_center[1] > anchor_location[1] and abs(text_center[0] - anchor_location[0]) < 75:
            dist = math.sqrt((text_center[0] - anchor_location[0])**2 + (text_center[1] - anchor_location[1])**2)
            if dist < min_dist:
                min_dist = dist
                found_text = text.strip()
    return found_text

def find_details_by_hybrid_anchor(ocr_results, known_companies):
    symbol_anchor_loc, strike1_anchor_loc = None, None
    found_company, found_strike_raw, found_time = None, None, None

    for (bbox, text, prob) in ocr_results:
        clean_text = text.lower().replace(' ','')
        if "symbol" in clean_text: symbol_anchor_loc = get_center(bbox)
        if "strike1" in clean_text: strike1_anchor_loc = get_center(bbox)

    # --- HYBRID COMPANY FINDING ---
    if symbol_anchor_loc:
        candidate_company = find_text_below(symbol_anchor_loc, ocr_results)
        if candidate_company and candidate_company.upper() in known_companies:
            found_company = candidate_company.upper()
    # Fallback: If positional logic fails, search the whole image
    if not found_company:
        all_text = " ".join([res[1].upper() for res in ocr_results])
        for company in known_companies:
            if company in all_text:
                found_company = company
                break

    # --- STRIKE PRICE FINDING ---
    if strike1_anchor_loc:
        found_strike_raw = find_text_below(strike1_anchor_loc, ocr_results)

    # --- TIME FINDING ---
    time_pattern = r'\d{1,2}[:;.]\d{2}'
    for (bbox, text, prob) in ocr_results:
        time_match = re.search(time_pattern, text)
        if time_match:
            found_time = time_match.group(0).replace(':', ';').replace('.', ';')
            break
            
    return found_company, found_strike_raw, found_time

def main():
    print("\n--- The Final, Hybrid Automated OCR Tool ---")
    
    # Load the list of companies from the text file
    if not os.path.exists("companies.txt"):
        print("ERROR: companies.txt not found. Please create it.")
        input("Press Enter to exit."); return
    with open("companies.txt", "r") as f:
        known_companies = [line.strip().upper() for line in f if line.strip()]
    print(f"Loaded {len(known_companies)} companies to search for.")

    fileDate = input("Enter the Date (e.g., 04-07-2025): ")
    
    print("\nProcessing files...")
    files_to_process = sorted([f for f in os.listdir('.') if f.lower().endswith('.png') and f.startswith('Screenshot')])

    for filename in files_to_process:
        print(f"Processing '{filename}'...")
        try:
            with Image.open(filename) as img:
                width, height = img.size
                cropped_img = img.crop((0, height * CROP_TOP_PERCENT, width, height * (1 - CROP_BOTTOM_PERCENT)))
            
            cropped_img_np = np.array(cropped_img)
            results = reader.readtext(cropped_img_np)
            company, strike_raw, time_str = find_details_by_hybrid_anchor(results, known_companies)
            
            if company and strike_raw and time_str:
                strike_str_cleaned = strike_raw.upper().replace('.00', '').replace('O','0')
                strike_num = re.search(r'\d+', strike_str_cleaned).group(0)
                option_type = "CE" if "CE" in strike_str_cleaned else "PE"
                
                new_filename = f"{fileDate} {company} {strike_num} {option_type} {time_str}.png"
                os.rename(filename, new_filename)
                print(f"  SUCCESS: Renamed to '{new_filename}'")
            else:
                fail_reason = []
                if not company: fail_reason.append("Company")
                if not strike_raw: fail_reason.append("Strike")
                if not time_str: fail_reason.append("Time")
                print(f"  FAILED: Could not find all details. Missing: {', '.join(fail_reason)}")

        except Exception as e:
            print(f"  ERROR: An unexpected error occurred: {e}")

    print("\n--- Renaming complete. ---")
    input("Press Enter to exit.")

if __name__ == "__main__":
    main()
