import os
import re
import sys
import easyocr
from PIL import Image
import numpy as np
from datetime import datetime
import multiprocessing as mp
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
import threading
from functools import partial

### --- PART 1: CONFIGURATION --- ###
print("\nInitializing EasyOCR... (This may take a moment on the first run)")
try:
    # Try GPU first
    reader = easyocr.Reader(['en'], gpu=True, download_enabled=False)
    print("EasyOCR Initialized on GPU.")
except Exception:
    print("GPU initialization failed. Falling back to CPU...")
    try:
        # CPU with optimizations
        reader = easyocr.Reader(['en'], gpu=False, download_enabled=False)
        print("EasyOCR Initialized on CPU.")
    except Exception:
        # Fallback without download disabled
        reader = easyocr.Reader(['en'], gpu=False)
        print("EasyOCR Initialized on CPU (with model download).")

CROP_TOP_PERCENT = 0.08 
CROP_BOTTOM_PERCENT = 0.20

# Performance optimization settings
OCR_WIDTH_THRESHOLD = 1200  # Resize images wider than this for faster processing
PARALLEL_PROCESSING = True  # Enable batch processing optimizations
CPU_CORES = 2  # Number of CPU cores to use
CPU_THREADS = 4  # Number of threads to use
BATCH_SIZE = 4  # Number of files to process in each batch 

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

def optimize_image_size(img, max_width=OCR_WIDTH_THRESHOLD):
    """
    Resize image for faster OCR processing while maintaining quality
    """
    width, height = img.size
    if width > max_width:
        # Calculate new height maintaining aspect ratio
        ratio = max_width / width
        new_height = int(height * ratio)
        img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
    return img

def enhance_image_for_ocr(img_array, fast_mode=True):
    """
    Enhance image for better OCR digit recognition with CPU optimization
    """
    from PIL import Image, ImageEnhance, ImageFilter
    
    # Convert to PIL Image if it's numpy array
    if isinstance(img_array, np.ndarray):
        img = Image.fromarray(img_array)
    else:
        img = img_array
    
    # Optimize size first for faster processing
    img = optimize_image_size(img)
    
    # Convert to grayscale for better digit recognition and faster processing
    img = img.convert('L')
    
    if fast_mode:
        # Fast CPU optimizations
        # Moderate contrast enhancement (less CPU intensive)
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(1.5)
        
        # Light sharpness enhancement
        enhancer = ImageEnhance.Sharpness(img)
        img = enhancer.enhance(1.3)
    else:
        # Full quality enhancements (slower)
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

### --- PARALLEL PROCESSING FUNCTIONS --- ###

def process_single_screenshot(args):
    """
    Process a single screenshot - designed for parallel execution
    """
    filename, fileDate, known_companies, reader_config = args
    
    # Initialize OCR reader for this process (each process needs its own)
    try:
        local_reader = easyocr.Reader(['en'], gpu=False, download_enabled=False)
    except:
        local_reader = easyocr.Reader(['en'], gpu=False)
    
    if not os.path.exists(filename):
        return None, f"File {filename} not found"
    
    try:
        # Process the image
        with Image.open(filename) as img:
            width, height = img.size
            cropped_img = img.crop((0, height * CROP_TOP_PERCENT, width, height * (1 - CROP_BOTTOM_PERCENT)))

        # CPU-optimized OCR processing
        enhanced_img = enhance_image_for_ocr(cropped_img, fast_mode=True)
        
        # Optimized OCR settings for faster CPU processing
        results = local_reader.readtext(
            enhanced_img, 
            detail=1, 
            paragraph=False,
            width_ths=0.7,
            height_ths=0.7,
            batch_size=1
        )
        
        # If no good results, try with better quality
        if not results or len(results) < 2:
            enhanced_img_slow = enhance_image_for_ocr(cropped_img, fast_mode=False)
            results_backup = local_reader.readtext(
                enhanced_img_slow, 
                detail=1, 
                paragraph=False,
                width_ths=0.5,
                height_ths=0.5
            )
            if len(results_backup) > len(results):
                results = results_backup

        # Extract information
        company, strike_num, option_type, time_str = find_all_details(results, known_companies)
        
        # Debug info
        debug_text = " ".join([res[1] for res in results])
        
        return {
            'filename': filename,
            'company': company,
            'strike_num': strike_num,
            'option_type': option_type,
            'time_str': time_str,
            'debug_text': debug_text,
            'success': True
        }, None
        
    except Exception as e:
        return None, f"Error processing {filename}: {str(e)}"

def process_batch_parallel(filenames, fileDate, known_companies):
    """
    Process a batch of screenshots in parallel using 2 cores and 4 threads
    """
    results = []
    
    # Prepare arguments for parallel processing
    process_args = [(filename, fileDate, known_companies, None) for filename in filenames]
    
    # Use ProcessPoolExecutor for CPU-intensive OCR work
    with ProcessPoolExecutor(max_workers=CPU_CORES) as process_executor:
        # Submit all jobs
        future_to_filename = {
            process_executor.submit(process_single_screenshot, args): args[0] 
            for args in process_args
        }
        
        # Collect results as they complete
        for future in future_to_filename:
            filename = future_to_filename[future]
            try:
                result, error = future.result(timeout=60)  # 60 second timeout per file
                if result:
                    results.append(result)
                else:
                    results.append({
                        'filename': filename,
                        'success': False,
                        'error': error
                    })
            except Exception as e:
                results.append({
                    'filename': filename,
                    'success': False,
                    'error': f"Processing timeout or error: {str(e)}"
                })
    
    return results

def move_file_threaded(file_info, fileDate):
    """
    Move processed file to appropriate folder - designed for threading
    """
    try:
        filename = file_info['filename']
        company = file_info['company']
        strike_num = file_info['strike_num']
        option_type = file_info['option_type']
        time_str = file_info['time_str']
        
        if company and strike_num and option_type and time_str and is_valid_time(time_str):
            # Create folder name
            folder_name = f"{strike_num} {option_type} {company}"
            
            # Thread-safe folder creation
            with threading.Lock():
                if not os.path.exists(folder_name):
                    os.makedirs(folder_name)
                    print(f"  📁 Created folder: '{folder_name}'")
            
            # Create filename and full path
            new_filename = f"{fileDate} {company} {strike_num} {option_type} {time_str}.png"
            full_path = os.path.join(folder_name, new_filename)
            
            if not os.path.exists(full_path):
                os.rename(filename, full_path)
                return f"✅ SUCCESS: Moved to '{folder_name}/{new_filename}'"
            else:
                print(f"  🔄 DUPLICATE FOUND: Exact duplicate exists in '{folder_name}'.")
                print(f"  🗑️ DELETING OLD FILE: Removing existing '{new_filename}'")
                os.remove(full_path)
                os.rename(filename, full_path)
                return f"✅ SUCCESS: Kept newer file and moved to '{folder_name}/{new_filename}'"
        else:
            # Handle failed processing
            fail_reason = []
            if not company: fail_reason.append("Company")
            if not strike_num or not option_type: fail_reason.append("Strike/Option")
            if not time_str:
                fail_reason.append("Time (not found)")
            elif not is_valid_time(time_str):
                fail_reason.append(f"Time (invalid value: '{time_str}')")
            
            try:
                os.remove(filename)
                return f"❌ MISREAD/INVALID: Could not find valid ({', '.join(fail_reason)}). DELETED '{filename}'"
            except OSError as e:
                return f"❌ Error deleting {filename}: {e}"
                
    except Exception as e:
        return f"❌ Error moving {filename}: {e}"

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

    print(f"Found {len(files_to_process)} files to process.")
    print(f"🚀 Using {CPU_CORES} CPU cores with {CPU_THREADS} threads for parallel processing")
    
    # Process files in batches for parallel processing
    processed_count = 0
    start_time = datetime.now()
    
    # Split files into batches
    batches = [files_to_process[i:i + BATCH_SIZE] for i in range(0, len(files_to_process), BATCH_SIZE)]
    
    for batch_num, batch_files in enumerate(batches, 1):
        print(f"\n🔄 Processing Batch {batch_num}/{len(batches)} ({len(batch_files)} files)")
        
        # Process batch in parallel (OCR processing)
        batch_results = process_batch_parallel(batch_files, fileDate, known_companies)
        
        # Move files using threading (I/O operations)
        move_tasks = []
        with ThreadPoolExecutor(max_workers=CPU_THREADS) as thread_executor:
            for result in batch_results:
                if result['success']:
                    # Show OCR debug info
                    debug_text = result.get('debug_text', '')
                    print(f"  🔍 {result['filename']}: '{debug_text[:60]}{'...' if len(debug_text) > 60 else ''}'")
                    if result.get('time_str'):
                        print(f"    ⏰ Extracted time: '{result['time_str']}'")
                    
                    # Submit file moving task
                    future = thread_executor.submit(move_file_threaded, result, fileDate)
                    move_tasks.append((future, result['filename']))
                else:
                    print(f"  ❌ {result['filename']}: {result.get('error', 'Unknown error')}")
            
            # Collect file moving results
            for future, filename in move_tasks:
                try:
                    move_result = future.result(timeout=30)
                    print(f"  {move_result}")
                except Exception as e:
                    print(f"  ❌ Error moving {filename}: {e}")
        
        # Update progress
        processed_count += len(batch_files)
        elapsed_time = (datetime.now() - start_time).total_seconds()
        avg_time_per_file = elapsed_time / processed_count
        remaining_files = len(files_to_process) - processed_count
        estimated_remaining = remaining_files * avg_time_per_file
        
        print(f"📊 Batch {batch_num} Complete | Overall Progress: {processed_count}/{len(files_to_process)} ({processed_count/len(files_to_process)*100:.1f}%)")
        print(f"⚡ Avg Speed: {avg_time_per_file:.1f}s/file | ETA: {estimated_remaining:.0f}s remaining")

    total_time = (datetime.now() - start_time).total_seconds()
    print(f"\n--- All files processed in {total_time:.1f} seconds ---")
    print(f"📈 Performance: {total_time/len(files_to_process):.1f} seconds per file")
    input("Press Enter to exit.")

if __name__ == "__main__":
    # Required for multiprocessing on Windows
    mp.set_start_method('spawn', force=True)
    main()