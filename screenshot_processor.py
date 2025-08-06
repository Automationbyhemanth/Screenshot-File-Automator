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

def fix_common_digit_errors(text):
    """
    Fix common OCR digit recognition errors
    """
    # More comprehensive digit corrections
    corrections = {
        # Zero corrections
        'O': '0', 'o': '0', 'Q': '0', 'D': '0', 'U': '0', 'C': '0',
        # One corrections
        'I': '1', 'l': '1', 'L': '1', '|': '1', 'J': '1', 'i': '1',
        # Two corrections
        'Z': '2', 'z': '2', 'R': '2',
        # Three corrections
        'E': '3', 'e': '3',
        # Four corrections
        'A': '4', 'a': '4',
        # Five corrections
        'S': '5', 's': '5', 'G': '5',
        # Six corrections
        'G': '6', 'g': '6', 'b': '6',
        # Seven corrections
        'T': '7', 't': '7', '?': '7',
        # Eight corrections
        'B': '8', '8': '8',
        # Nine corrections
        'g': '9', 'q': '9',
    }
    
    result = text
    for wrong, right in corrections.items():
        result = result.replace(wrong, right)
    
    return result

def extract_time_advanced(ocr_results):
    """
    Advanced time extraction with multiple strategies
    """
    found_times = []
    
    # Strategy 1: Direct pattern matching in individual text blocks
    for result in ocr_results:
        text = result[1].upper().strip()
        confidence = result[2] if len(result) > 2 else 0.5
        
        # Clean the text first
        cleaned_text = fix_common_digit_errors(text)
        
        # Multiple time patterns with different separators
        time_patterns = [
            r'\b([0-9]|1[0-5])[:;.]([0-5][0-9])\b',  # Standard time format
            r'\b([0-9]|1[0-5])[:;.]([0-9][0-9])\b',   # Allow any two digits for minutes
            r'\b(9|10|11|12|13|14|15)[:;.]([0-5][0-9])\b',  # Only valid hours
        ]
        
        for pattern in time_patterns:
            matches = re.findall(pattern, cleaned_text)
            for hour, minute in matches:
                try:
                    h, m = int(hour), int(minute)
                    if 9 <= h <= 15 and 0 <= m <= 59:
                        time_str = f"{h};{m:02d}"
                        found_times.append((time_str, confidence))
                except ValueError:
                    continue
    
    # Strategy 2: Fix problematic readings like "71;50" -> "11;50"
    full_text = " ".join([res[1] for res in ocr_results])
    
    # Look for patterns that might be misread times
    problematic_patterns = [
        r'\b([67])([01])[:;.]([0-5][0-9])\b',  # 71, 70, 61, 60 -> 11, 10, 11, 10
        r'\b([789])([0-9])[:;.]([0-5][0-9])\b',  # 8x, 9x -> 1x
        r'\b([0-9])([0-9])[:;.]([6-9][0-9])\b',  # xx:6x, xx:7x, xx:8x, xx:9x -> xx:0x, xx:1x
    ]
    
    for pattern in problematic_patterns:
        matches = re.findall(pattern, full_text)
        for match in matches:
            try:
                first_digit, second_digit, minute_part = match
                
                # Fix hour part
                if first_digit in ['6', '7']:  # 6x, 7x -> 1x
                    corrected_hour = '1' + second_digit
                elif first_digit in ['8', '9']:  # 8x, 9x -> 1x  
                    corrected_hour = '1' + second_digit
                else:
                    corrected_hour = first_digit + second_digit
                
                # Fix minute part - if minutes > 59, likely OCR error
                minute_val = int(minute_part)
                if minute_val >= 60:
                    # Common errors: 60->00, 70->10, 80->30, 90->30
                    if minute_part.startswith('6'):
                        corrected_minute = '0' + minute_part[1]
                    elif minute_part.startswith('7'):
                        corrected_minute = '1' + minute_part[1]
                    elif minute_part.startswith('8'):
                        corrected_minute = '3' + minute_part[1]
                    elif minute_part.startswith('9'):
                        corrected_minute = '3' + minute_part[1]
                    else:
                        corrected_minute = minute_part
                else:
                    corrected_minute = minute_part
                
                h, m = int(corrected_hour), int(corrected_minute)
                if 9 <= h <= 15 and 0 <= m <= 59:
                    time_str = f"{h};{m:02d}"
                    found_times.append((time_str, 0.7))  # Medium confidence for corrections
            except (ValueError, IndexError):
                continue
    
    # Strategy 3: Character-by-character correction
    corrected_full_text = fix_common_digit_errors(full_text.upper())
    
    time_patterns = [
        r'\b([0-9]|1[0-5])[:;.]([0-5][0-9])\b',
        r'\b(9|10|11|12|13|14|15)[:;.]([0-9]{2})\b',
    ]
    
    for pattern in time_patterns:
        matches = re.findall(pattern, corrected_full_text)
        for hour, minute in matches:
            try:
                h, m = int(hour), int(minute)
                if 9 <= h <= 15 and 0 <= m <= 59:
                    time_str = f"{h};{m:02d}"
                    found_times.append((time_str, 0.9))  # High confidence for corrected text
            except ValueError:
                continue
    
    # Strategy 4: Look for separated numbers that might be times
    number_pattern = r'\b([0-9]|1[0-5])\s+([0-5][0-9])\b'
    matches = re.findall(number_pattern, corrected_full_text)
    for hour, minute in matches:
        try:
            h, m = int(hour), int(minute)
            if 9 <= h <= 15 and 0 <= m <= 59:
                time_str = f"{h};{m:02d}"
                found_times.append((time_str, 0.6))  # Lower confidence for separated numbers
        except ValueError:
            continue
    
    # Strategy 5: Try to fix specific known bad readings
    # Handle cases like "71;50" where 7 should be 1
    bad_reading_fixes = [
        (r'\b7([0-5])[:;.]([0-5][0-9])\b', r'1\1;\2'),  # 71:50 -> 11:50
        (r'\b6([0-5])[:;.]([0-5][0-9])\b', r'1\1;\2'),  # 61:30 -> 11:30
        (r'\b([0-9]|1[0-5])[:;.]7([0-9])\b', r'\1;1\2'),  # 10:70 -> 10:10
        (r'\b([0-9]|1[0-5])[:;.]6([0-9])\b', r'\1;0\2'),  # 10:60 -> 10:00
    ]
    
    for bad_pattern, fix_pattern in bad_reading_fixes:
        fixed_text = re.sub(bad_pattern, fix_pattern, full_text)
        if fixed_text != full_text:
            # Look for valid times in the fixed text
            time_pattern = r'\b([0-9]|1[0-5])[:;.]([0-5][0-9])\b'
            matches = re.findall(time_pattern, fixed_text)
            for hour, minute in matches:
                try:
                    h, m = int(hour), int(minute)
                    if 9 <= h <= 15 and 0 <= m <= 59:
                        time_str = f"{h};{m:02d}"
                        found_times.append((time_str, 0.8))  # Good confidence for pattern fixes
                except ValueError:
                    continue
    
    # Return the most confident time found
    if found_times:
        # Remove duplicates
        unique_times = {}
        for time_str, confidence in found_times:
            if time_str not in unique_times or unique_times[time_str] < confidence:
                unique_times[time_str] = confidence
        
        # Sort by confidence
        sorted_times = sorted(unique_times.items(), key=lambda x: x[1], reverse=True)
        return sorted_times[0][0]
    
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
            
            # Debug: Show what OCR detected
            debug_text = " ".join([res[1] for res in results])
            print(f"  🔍 OCR detected: '{debug_text[:100]}{'...' if len(debug_text) > 100 else ''}'")
            if time_str:
                print(f"  ⏰ Extracted time: '{time_str}'")

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