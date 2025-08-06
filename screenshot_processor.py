import os
import re
import sys
import easyocr
from PIL import Image
import numpy as np
from datetime import datetime

# --- LIBRARIES FOR LICENSE VERIFICATION ---
try:
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials
except ImportError:
    print("ERROR: 'gspread' or 'oauth2client' not found. Please run: pip install gspread oauth2client")
    sys.exit()

### --- RESOURCE PATH HELPER (for making the script an executable .exe) --- ###
def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

### --- LICENSE VERIFICATION FUNCTION --- ###
def verify_license():
    """
    Connects to Google Sheets to verify the user's Name, Email, and License Key.
    """
    print("\n🔐 License Verification Required")
    name = input("Enter your Name: ").strip()
    email = input("Enter your Email: ").strip()
    license_key = input("Enter your License Key: ").strip()

    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        json_keyfile_path = resource_path("Screenshot-access.json")
        if not os.path.exists(json_keyfile_path):
            print(f"❌ FATAL ERROR: The license credentials file 'Screenshot-access.json' was not found.")
            return False

        creds = ServiceAccountCredentials.from_json_keyfile_name(json_keyfile_path, scope)
        client = gspread.authorize(creds)
        
        sheet = client.open("Screenshot License Access").sheet1
        records = sheet.get_all_records()

        for row in records:
            if row.get("Name","").strip().lower() == name.lower() and \
               row.get("Email","").strip().lower() == email.lower() and \
               row.get("License Key","").strip() == license_key:
                
                print("✅ License Verified!")
                return True

        print("❌ Access Denied: License details not found or do not match.")
        return False

    except gspread.exceptions.SpreadsheetNotFound:
        print("❌ FATAL ERROR: The Google Sheet named 'Screenshot License Access' was not found.")
        print("   Please ensure the sheet exists and is shared with the client_email from your JSON file.")
        return False
    except Exception as e:
        print(f"❌ An error occurred during license verification: {e}")
        return False

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
    print("\n--- Secure Automated Batch Processor ---")
    
    # --- LICENSE CHECK AT THE START ---
    if not verify_license():
        input("Press Enter to exit.")
        return

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
                new_filename = f"{fileDate} {company} {strike_num} {option_type} {time_str}.png"
                if not os.path.exists(new_filename):
                    os.rename(filename, new_filename)
                    print(f"  ✅ SUCCESS: Renamed to '{new_filename}'")
                else:
                    try:
                        print(f"  - INFO: Duplicate found. Replacing existing '{new_filename}' with this new screenshot.")
                        os.remove(new_filename)
                        os.rename(filename, new_filename)
                        print(f"  ✅ SUCCESS: Replaced old file and renamed to '{new_filename}'")
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