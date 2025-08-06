# Screenshot Processor

An automated batch processor for screenshot files that uses OCR (Optical Character Recognition) to extract trading information and rename files accordingly.

## Features

- **License Verification**: Secure license checking via Google Sheets
- **OCR Processing**: Uses EasyOCR for text extraction from screenshots
- **Intelligent Parsing**: Extracts company symbols, strike prices, option types, and timestamps
- **Automated Renaming**: Renames files based on extracted information
- **Batch Processing**: Processes multiple screenshots at once
- **GPU/CPU Support**: Automatically falls back to CPU if GPU is unavailable

## Requirements

- Python 3.7+
- Required Python packages (see `requirements.txt`)
- Google Service Account credentials (`Screenshot-access.json`)
- Company symbols list (`companies.txt`)

## Installation

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Set up Google Sheets API:
   - Create a Google Service Account
   - Download the JSON credentials file
   - Rename it to `Screenshot-access.json`
   - Place it in the same directory as the script

3. Create a Google Sheet named "Screenshot License Access" with columns:
   - Name
   - Email
   - License Key

4. Share the Google Sheet with the client_email from your JSON credentials file

## Usage

1. Place screenshot files (PNG, JPG, JPEG) starting with "Screenshot" in the same directory
2. Ensure `companies.txt` contains the stock symbols you want to detect
3. Run the script:
```bash
python screenshot_processor.py
```

4. Follow the prompts:
   - Enter your license credentials
   - Enter the date for the batch processing
   - The script will process all screenshot files automatically

## File Structure

```
├── screenshot_processor.py    # Main script
├── requirements.txt          # Python dependencies
├── companies.txt            # List of company symbols to detect
├── Screenshot-access.json   # Google API credentials (you need to create this)
└── README.md               # This file
```

## How It Works

1. **License Verification**: Connects to Google Sheets to verify user credentials
2. **Image Processing**: Crops screenshots to focus on relevant areas
3. **OCR Extraction**: Uses EasyOCR to extract text from images
4. **Pattern Matching**: Searches for:
   - Company symbols (from `companies.txt`)
   - Strike prices (3-6 digit numbers)
   - Option types (CE/PE)
   - Timestamps (HH:MM format between 9:00-15:59)
5. **File Renaming**: Renames files to format: `{Date} {Company} {Strike} {OptionType} {Time}.png`

## Configuration

### Cropping Settings
- `CROP_TOP_PERCENT = 0.08` (crops top 8% of image)
- `CROP_BOTTOM_PERCENT = 0.20` (crops bottom 20% of image)

### Time Validation
- Only accepts times between 9:00 and 15:59 (trading hours)
- Rejects invalid OCR readings like "71:50"

## Error Handling

- Files that cannot be processed are automatically deleted
- Duplicate files are replaced with newer versions
- Comprehensive error logging for troubleshooting

## Building Executable

To create a standalone executable with PyInstaller:

```bash
pip install pyinstaller
pyinstaller --onefile --add-data "Screenshot-access.json;." --add-data "companies.txt;." screenshot_processor.py
```

## Security Notes

- License verification prevents unauthorized usage
- Google API credentials should be kept secure
- The script requires internet access for license verification

## Troubleshooting

1. **GPU Issues**: Script automatically falls back to CPU if GPU initialization fails
2. **Missing Dependencies**: Install all packages from `requirements.txt`
3. **Google Sheets Access**: Ensure the sheet is shared with your service account email
4. **OCR Accuracy**: Adjust cropping percentages if OCR is missing information

## Support

For technical support or license issues, contact the script administrator.
