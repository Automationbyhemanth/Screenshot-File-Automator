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
        # Handle different separators
        if ';' in time_str:
            hour, minute = map(int, time_str.split(';'))
        elif ':' in time_str:
            hour, minute = map(int, time_str.split(':'))
        elif '.' in time_str:
            hour, minute = map(int, time_str.split('.'))
        else:
            return False
            
        if 9 <= hour <= 15 and 0 <= minute <= 59:
            return True
        else:
            return False
    except (ValueError, IndexError):
        return False

def enhance_image_for_ocr(img_array):
    """
    Enhance image for better OCR digit recognition
    """
    from PIL import Image, ImageEnhance, ImageFilter
    import cv2
    
    # Convert to PIL Image if it's numpy array
    if isinstance(img_array, np.ndarray):
        img = Image.fromarray(img_array)
    else:
        img = img_array
    
    # Convert to grayscale for better digit recognition
    img = img.convert('L')
    
    # Enhance contrast
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(2.0)
    
    # Enhance sharpness
    enhancer = ImageEnhance.Sharpness(img)
    img = enhancer.enhance(2.0)
    
    # Apply slight blur to reduce noise
    img = img.filter(ImageFilter.MedianFilter(size=3))
    
    return np.array(img)

def extract_time_advanced(ocr_results):
    """
    Advanced time extraction with multiple strategies
    """
    found_times = []
    
    # Strategy 1: Look for time patterns in individual text blocks
    for result in ocr_results:
        text = result[1].upper().strip()
        
        # Multiple time patterns with different separators
        time_patterns = [
            r'\b([0-9]|1[0-5])[:;.]([0-5][0-9])\b',  # Standard time format
            r'\b([0-9]|1[0-5])[:;.]([0-9][0-9])\b',   # Allow any two digits for minutes
            r'\b(9|10|11|12|13|14|15)[:;.]([0-5][0-9])\b',  # Only valid hours
            r'\b([0-9]{1,2})[:;.]([0-9]{2})\b',       # General pattern
        ]
        
        for pattern in time_patterns:
            matches = re.findall(pattern, text)
            for hour, minute in matches:
                try:
                    h, m = int(hour), int(minute)
                    if 9 <= h <= 15 and 0 <= m <= 59:
                        time_str = f"{h};{m:02d}"
                        found_times.append((time_str, result[0]))  # Include confidence/position
                except ValueError:
                    continue
    
    # Strategy 2: Look in concatenated text with character corrections
    full_text = " ".join([res[1] for res in ocr_results])
    corrected_text = full_text.upper()
    
    # Common OCR misreadings for digits
    corrections = {
        'O': '0', 'o': '0', 'Q': '0', 'D': '0',
        'I': '1', 'l': '1', 'L': '1', '|': '1',
        'Z': '2', 'z': '2',
        'S': '5', 's': '5',
        'G': '6', 'g': '6',
        'T': '7', 't': '7',
        'B': '8', 'b': '8',
    }
    
    for wrong, right in corrections.items():
        corrected_text = corrected_text.replace(wrong, right)
    
    # Apply time patterns to corrected text
    time_patterns = [
        r'\b([0-9]|1[0-5])[:;.]([0-5][0-9])\b',
        r'\b(9|10|11|12|13|14|15)[:;.]([0-9]{2})\b',
    ]
    
    for pattern in time_patterns:
        matches = re.findall(pattern, corrected_text)
        for hour, minute in matches:
            try:
                h, m = int(hour), int(minute)
                if 9 <= h <= 15 and 0 <= m <= 59:
                    time_str = f"{h};{m:02d}"
                    found_times.append((time_str, 1.0))  # High confidence for corrected text
            except ValueError:
                continue
    
    # Strategy 3: Look for partial time patterns and try to reconstruct
    # Look for patterns like "1 30" or "14 45" that might be times
    number_pattern = r'\b([0-9]|1[0-5])\s+([0-5][0-9])\b'
    matches = re.findall(number_pattern, corrected_text)
    for hour, minute in matches:
        try:
            h, m = int(hour), int(minute)
            if 9 <= h <= 15 and 0 <= m <= 59:
                time_str = f"{h};{m:02d}"
                found_times.append((time_str, 0.8))  # Medium confidence
        except ValueError:
            continue
    
    # Return the most confident time found
    if found_times:
        # Sort by confidence (second element in tuple)
        found_times.sort(key=lambda x: x[1], reverse=True)
        return found_times[0][0]
    
    return None

def find_all_details(ocr_results, known_companies):
    found_company, found_strike_num, found_option_type, found_time = None, None, None, None

    full_text = " ".join([res[1] for res in ocr_results])
    text_for_search = full_text.upper().replace('I', '1').replace('L', '1')

    # Company detection
    for company_symbol in known_companies:
        if re.search(r'\b' + re.escape(company_symbol) + r'\b', text_for_search):
            found_company = company_symbol
            break 

    # Strike and option type detection with better OCR corrections
    corrected_text = text_for_search.replace('O', '0').replace('o', '0').replace('Q', '0')
    strike_pattern = r'(\d{3,6})[^A-Z]*(CE|PE)'
    strike_match = re.search(strike_pattern, corrected_text)
    if strike_match:
        strike_raw = strike_match.group(1)
        if len(strike_raw) > 4 and strike_raw.endswith("00"):
            strike_int = int(strike_raw) // 100
        else:
            strike_int = int(strike_raw)
        found_strike_num = str(strike_int)
        found_option_type = strike_match.group(2)

    # Use advanced time extraction
    found_time = extract_time_advanced(ocr_results)

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

            # Enhance image for better OCR
            enhanced_img = enhance_image_for_ocr(cropped_img)
            
            # First pass with enhanced image
            results = reader.readtext(enhanced_img, detail=1, paragraph=False)
            
            # If no good results, try with original cropped image
            if not results or len(results) < 3:
                cropped_img_np = np.array(cropped_img)
                results_backup = reader.readtext(cropped_img_np, detail=1, paragraph=False)
                if len(results_backup) > len(results):
                    results = results_backup

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