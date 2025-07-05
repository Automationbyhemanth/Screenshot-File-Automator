import os
import re
import easyocr
from PIL import Image
import numpy as np # We need this library for the fix

### --- PART 1: CONFIGURATION --- ###
print("Initializing EasyOCR... (This may take a moment on the first run)")
reader = easyocr.Reader(['en'], gpu=False)
print("EasyOCR Initialized.")

# --- CROP SETTINGS ---
CROP_TOP_PERCENT = 0.20
CROP_BOTTOM_PERCENT = 0.20

### --- PART 2: THE CORRECTED LOGIC --- ###

def find_first_time(ocr_results):
    time_pattern = r'\d{1,2}[:;.]\d{2}'
    for (bbox, text, prob) in ocr_results:
        match = re.search(time_pattern, text)
        if match:
            found_time = match.group(0)
            return found_time.replace(':', ';').replace('.', ';')
    return None

def main():
    print("\n--- The Final, Corrected, Automated OCR Tool ---")
    
    fileDate = input("Enter the Date (e.g., 04-07-2025): ")
    company = input("Enter the Company Name (e.g., ABB): ")
    strike = input("Enter the Strike Price (e.g., 6200): ")
    optionType = input("Enter Option Type (CE or PE): ")
    print("\nProcessing files...")

    files_to_process = sorted([f for f in os.listdir('.') if f.lower().endswith('.png') and f.startswith('Screenshot')])

    if not files_to_process:
        print("No 'Screenshot (...).png' files found to rename.")
        input("Press Enter to exit.")
        return

    for filename in files_to_process:
        print(f"Processing '{filename}'...")
        try:
            with Image.open(filename) as img:
                width, height = img.size
                left = 0
                top = height * CROP_TOP_PERCENT
                right = width
                bottom = height * (1 - CROP_BOTTOM_PERCENT)
                
                cropped_img = img.crop((left, top, right, bottom))
            
            # THE FIX IS HERE: We convert the cropped image to the correct format (a numpy array).
            cropped_img_np = np.array(cropped_img)
            
            # Now we give the correctly formatted data to EasyOCR.
            results = reader.readtext(cropped_img_np)
            time_str = find_first_time(results)
            
            if time_str:
                new_filename = f"{fileDate} {company} {strike} {optionType} {time_str}.png"
                os.rename(filename, new_filename)
                print(f"  SUCCESS: Renamed to '{new_filename}'")
            else:
                print(f"  FAILED: Could not find any time in the cropped image.")

        except Exception as e:
            print(f"  ERROR: An unexpected error occurred: {e}")

    print("\n--- Renaming complete. ---")
    input("Press Enter to exit.")

if __name__ == "__main__":
    main()