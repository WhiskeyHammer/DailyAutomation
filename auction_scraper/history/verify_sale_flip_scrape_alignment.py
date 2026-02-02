import csv
import os
import glob

# --- CONFIGURATION ---

# Get the project root directory (two levels up from this script)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))

# 1. The Master Input File (Where we got the leads)
# Find the most recent tax_sales CSV file
PAST_AUCTIONS_DIR = os.path.join(PROJECT_ROOT, "data", "past_auctions")
tax_sales_files = glob.glob(os.path.join(PAST_AUCTIONS_DIR, "tax_sales_*.csv"))
SOURCE_CSV = sorted(tax_sales_files)[-1] if tax_sales_files else os.path.join(PAST_AUCTIONS_DIR, "tax_sales.csv")

# 2. The Output Files (Where we stored the results)
# Using glob patterns to find the latest timestamped files
PARCEL_HISTORY_DIR = os.path.join(PROJECT_ROOT, "data", "parcel_history")
TARGET_FILES = [
    os.path.join(PARCEL_HISTORY_DIR, "duval_assessment_and_flips_*.csv"),
    os.path.join(PARCEL_HISTORY_DIR, "nassau_assessment_and_flips_*.csv"),
    os.path.join(PARCEL_HISTORY_DIR, "clay_assessment_and_flips_*.csv"),
    os.path.join(PARCEL_HISTORY_DIR, "baker_assessment_and_flips_*.csv")
]

# --- LOGIC ---

def normalize_pid(pid):
    """
    Standardizes Parcel IDs for comparison.
    - Removes surrounding whitespace.
    - Returns None if empty or 'N/A'.
    """
    if not pid:
        return None
    cleaned = pid.strip()
    if cleaned.lower() in ["n/a", "", "parcel id"]:
        return None
    return cleaned

def load_processed_pids(file_patterns):
    """
    Reads all Target Files (using glob patterns) and gathers every Parcel ID found.
    For each pattern, uses the most recent file if multiple matches exist.
    Returns: A set of normalized Parcel IDs.
    """
    processed = set()
    files_checked = 0

    print(f"--- Loading Data from {len(file_patterns)} Output File Patterns ---")

    for pattern in file_patterns:
        # Find all files matching the pattern
        matching_files = glob.glob(pattern)
        
        if not matching_files:
            print(f"[WARN] No files found matching: {pattern}")
            continue
        
        # Use the most recent file (sorted alphabetically, timestamps sort correctly)
        filename = sorted(matching_files)[-1]
        
        try:
            with open(filename, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                count = 0
                for row in reader:
                    # Adjust column name if you changed it in the scraper
                    # We expect "Parcel ID" based on previous scripts
                    raw_pid = row.get("Parcel ID")
                    
                    pid = normalize_pid(raw_pid)
                    if pid:
                        processed.add(pid)
                        count += 1
                
                print(f"  -> {filename}: Loaded {count} records")
                files_checked += 1
        except Exception as e:
            print(f"[ERR] Could not read {filename}: {e}")

    print(f"Total Unique IDs Processed: {len(processed)}\n")
    return processed

def verify_against_source(source_file, processed_set):
    """
    Iterates through Source CSV and checks if each ID exists in the processed_set.
    Prints missing items.
    """
    if not os.path.exists(source_file):
        print(f"Error: Source file {source_file} not found.")
        return

    missing_count = 0
    total_count = 0

    print(f"--- Verifying against Source: {source_file} ---")

    with open(source_file, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        
        # Verify Source has Parcel ID column
        if "Parcel ID" not in reader.fieldnames:
             print(f"Error: 'Parcel ID' column missing in {source_file}. Found: {reader.fieldnames}")
             return

        print(f"{'STATUS':<10} | {'COUNTY':<10} | {'PARCEL ID':<25} | {'LINK'}")
        print("-" * 80)

        for row in reader:
            raw_pid = row.get("Parcel ID")
            county = row.get("County", "Unknown")
            link = row.get("Link", "N/A")
            
            pid = normalize_pid(raw_pid)
            
            # Skip rows that don't have a valid PID in the source (bad data)
            if not pid:
                continue
            
            total_count += 1

            if pid not in processed_set:
                missing_count += 1
                print(f"{'MISSING':<10} | {county:<10} | {pid:<25} | {link}")

    print("-" * 80)
    print(f"Verification Complete.")
    print(f"Total Rows in Source: {total_count}")
    print(f"Successfully Scraped: {total_count - missing_count}")
    print(f"Missing / Failed:     {missing_count}")
    
    if missing_count == 0:
        print("\nSUCCESS: All records accounted for!")
    else:
        print(f"\nACTION REQUIRED: You have {missing_count} missing records.")

# --- MAIN EXECUTION ---

if __name__ == "__main__":
    # 1. Load all IDs we have already scraped
    found_pids = load_processed_pids(TARGET_FILES)
    
    # 2. Compare against the master list
    verify_against_source(SOURCE_CSV, found_pids)