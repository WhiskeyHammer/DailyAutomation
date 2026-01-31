import csv
import os

# --- CONFIGURATION ---

# 1. The Master Input File (Where we got the leads)
SOURCE_CSV = "tax_sales_2026-01-29.csv"

# 2. The Output Files (Where we stored the results)
# Add or remove files from this list as needed.
TARGET_FILES = [
    "duval_assessment_and_flips.csv",
    "nassau_assessment_and_flips.csv",
    "clay_assessment_and_flips.csv",
    "baker_assessment_and_flips.csv"
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

def load_processed_pids(file_list):
    """
    Reads all Target Files and gathers every Parcel ID found.
    Returns: A set of normalized Parcel IDs.
    """
    processed = set()
    files_checked = 0

    print(f"--- Loading Data from {len(file_list)} Output Files ---")

    for filename in file_list:
        if not os.path.exists(filename):
            print(f"[WARN] File not found: {filename}")
            continue
        
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