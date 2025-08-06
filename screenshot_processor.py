import os
import re
import sys
import easyocr
from PIL import Image
import numpy as np
from datetime import datetime

### --- PART 1: CONFIGURATION --- ###
print("\nInitializing EasyOCR... (This may take a moment on the first run)")
try:
    reader = easyocr.Reader(['en'], gpu=True)
    print("EasyOCR Initialized on GPU.")
except Exception:
    print("GPU initialization failed. Falling back to CPU...")
    reader = easyocr.Reader(['en'], gpu=False)
    print("EasyOCR Initialized on CPU.")

CROP_TOP_PERCENT = 0.08 
CROP_BOTTOM_PERCENT = 0.20 

### --- PART 2: THE VALIDATED LOGIC --- ###

def is_valid_time(time_str):
    """
    Checks if a time string is logically valid (e.g., 9:00-15:59).
    This will reject misreadings like '71;50'.
    """
    try:
        hour, minute = map(int, time_str.split(';'))
        if 9 <= hour <= 15 and 0 <= minute <= 59:
            return True
        else:
            return False
    except (ValueError, IndexError):
        return False

def find_all_details(ocr_results, known_companies):
    # This function is taken directly from the script you provided
    found_company, found_strike_num, found_option_type, found_time = None, None, None, None

    full_text = " ".join([res[1] for res in ocr_results])
    text_for_search = full_text.upper().replace('I', '1').replace('L', '1')

    for company_symbol in known_companies:
        if re.search(r'\b' + re.escape(company_symbol) + r'\b', text_for_search):
            found_company = company_symbol
            break 

    strike_pattern = r'(\d{3,6})[^A-Z]*(CE|PE)'
    strike_match = re.search(strike_pattern, text_for_search.replace('O', '0'))
    if strike_match:
        strike_raw = strike_match.group(1)
        if len(strike_raw) > 4 and strike_raw.endswith("00"):
            strike_int = int(strike_raw) // 100
        else:
            strike_int = int(strike_raw)
        found_strike_num = str(strike_int)
        found_option_type = strike_match.group(2)

    time_pattern = r'(\d{1,2})[:;.](\d{2})'
    time_match = re.search(time_pattern, text_for_search)
    if time_match:
        hour, minute = time_match.groups()
        found_time = f"{hour};{minute}"

    return found_company, found_strike_num, found_option_type, found_time

### --- MAIN EXECUTION BLOCK --- ###
def main():
    print("\n--- Automated Batch Processor ---")
    
    print("\n--- Starting File Processing ---")
    if not os.path.exists("companies.txt"):
        print("ERROR: The 'companies.txt' file was not found in this folder.")
        input("Press Enter to exit."); return
    with open("companies.txt", "r") as f:
        known_companies = [line.strip().upper() for line in f if line.strip()]
    print(f"Loaded {len(known_companies)} company symbols to search for.")

    fileDate = input("Enter the Date for this batch (e.g., 07-08-2025): ")
    
    print("\nProcessing all 'Screenshot...' files in the current folder...")
    files_to_process = sorted([f for f in os.listdir('.') if f.lower().endswith(('.png', '.jpg', '.jpeg')) and f.lower().startswith('screenshot')])

    if not files_to_process:
        print("No 'Screenshot...' files found to process.")
        input("Press Enter to exit."); return

    for filename in files_to_process:
        if not os.path.exists(filename): continue
        print(f"Processing '{filename}'...")
        try:
            with Image.open(filename) as img:
                width, height = img.size
                cropped_img = img.crop((0, height * CROP_TOP_PERCENT, width, height * (1 - CROP_BOTTOM_PERCENT)))

            cropped_img_np = np.array(cropped_img)
            results = reader.readtext(cropped_img_np, detail=1, paragraph=False)

            company, strike_num, option_type, time_str = find_all_details(results, known_companies)

            if company and strike_num and option_type and time_str and is_valid_time(time_str):
                # Create folder name in format: "Strike OptionType Company"
                folder_name = f"{strike_num} {option_type} {company}"
                
                # Create the folder if it doesn't exist
                if not os.path.exists(folder_name):
                    os.makedirs(folder_name)
                    print(f"  📁 Created folder: '{folder_name}'")
                
                # Create filename and full path
                new_filename = f"{fileDate} {company} {strike_num} {option_type} {time_str}.png"
                full_path = os.path.join(folder_name, new_filename)
                
                if not os.path.exists(full_path):
                    os.rename(filename, full_path)
                    print(f"  ✅ SUCCESS: Moved to '{folder_name}/{new_filename}'")
                else:
                    try:
                        print(f"  - INFO: Duplicate found. Replacing existing file in '{folder_name}'.")
                        os.remove(full_path)
                        os.rename(filename, full_path)
                        print(f"  ✅ SUCCESS: Replaced old file and moved to '{folder_name}/{new_filename}'")
                    except OSError as e:
                        print(f"    - Error during replacement: {e}")
            else:
                fail_reason = []
                if not company: fail_reason.append("Company")
                if not strike_num or not option_type: fail_reason.append("Strike/Option")
                if not time_str:
                    fail_reason.append("Time (not found)")
                elif not is_valid_time(time_str):
                    fail_reason.append(f"Time (invalid value: '{time_str}')")
                
                print(f"  ❌ MISREAD/INVALID: Could not find valid ({', '.join(fail_reason)}).")
                try:
                    os.remove(filename)
                    print(f"  - DELETED '{filename}' because it was unreadable or contained invalid data.")
                except OSError as e:
                    print(f"    - Error while deleting misread file: {e}")

        except Exception as e:
            print(f"  ❌ ERROR: An unexpected error occurred: {e}")

    print("\n--- All files processed. ---")
    input("Press Enter to exit.")

if __name__ == "__main__":
    main()