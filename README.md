# Screenshot Processor

An automated batch processor for screenshot files that uses OCR (Optical Character Recognition) to extract trading information and rename files accordingly.

## Features

- **OCR Processing**: Uses EasyOCR for text extraction from screenshots
- **Intelligent Parsing**: Extracts company symbols, strike prices, option types, and timestamps
- **Automated Renaming**: Renames files based on extracted information
- **Auto Folder Organization**: Creates folders by strike/option/company and moves files accordingly
- **Batch Processing**: Processes multiple screenshots at once
- **GPU/CPU Support**: Automatically falls back to CPU if GPU is unavailable

## Requirements

- Python 3.7+
- Required Python packages (see `requirements.txt`)
- Company symbols list (`companies.txt`)

## Installation

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Ensure you have the `companies.txt` file with stock symbols you want to detect

## Usage

1. Place screenshot files (PNG, JPG, JPEG) starting with "Screenshot" in the same directory
2. Ensure `companies.txt` contains the stock symbols you want to detect
3. Run the script:
```bash
python screenshot_processor.py
```

4. Follow the prompts:
   - Enter the date for the batch processing
   - The script will process all screenshot files automatically

## File Structure

```
├── screenshot_processor.py    # Main script
├── requirements.txt          # Python dependencies
├── companies.txt            # List of company symbols to detect
├── README.md               # This file
└── [Generated Folders]      # Auto-created folders like "400 PE PFC", "5100 CE ABB", etc.
    ├── [Organized Screenshots]  # Screenshots moved to appropriate folders
```

## How It Works

1. **Image Processing**: Crops screenshots to focus on relevant areas
2. **OCR Extraction**: Uses EasyOCR to extract text from images
3. **Pattern Matching**: Searches for:
   - Company symbols (from `companies.txt`)
   - Strike prices (3-6 digit numbers)
   - Option types (CE/PE)
   - Timestamps (HH:MM format between 9:00-15:59)
4. **Folder Creation**: Creates folders named: `{Strike} {OptionType} {Company}` (e.g., "400 PE PFC", "5100 CE ABB")
5. **File Organization**: Renames and moves files to appropriate folders with format: `{Date} {Company} {Strike} {OptionType} {Time}.png`

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

## Troubleshooting

1. **GPU Issues**: Script automatically falls back to CPU if GPU initialization fails
2. **Missing Dependencies**: Install all packages from `requirements.txt`
3. **OCR Accuracy**: Adjust cropping percentages if OCR is missing information
4. **Company Detection**: Update `companies.txt` with the stock symbols you need to detect

## Support

For technical support, refer to the documentation or modify the script as needed.
