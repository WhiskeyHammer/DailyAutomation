import subprocess
import sys
import time
import os
import logging
from datetime import datetime

# --- CONFIGURATION ---

# Define the scripts to run in order
SCRIPTS = {
    "Step 1 (Auctions)": "auction_scraper/history/past_tax_sale_scrape.py",  
    "Step 2 (Parcel History)": "auction_scraper/history/parcel_history_scrape.py",  
    "Step 3 (Verify)": "auction_scraper/history/verify_sale_flip_scrape_alignment.py"
}

# Generate timestamp for output files (down to the second)
RUN_TIMESTAMP = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')

# Logs for the runner itself
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
os.makedirs(LOG_DIR, exist_ok=True)
RUNNER_LOG = os.path.join(LOG_DIR, f"pipeline_runner_{RUN_TIMESTAMP}.log")

# --- LOGGING SETUP ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [RUNNER] - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(RUNNER_LOG, mode='w', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# --- EXECUTION ENGINE ---

def run_script(step_name, script_path_relative):
    """
    Runs a python script as a subprocess and waits for it to finish.
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    script_path = os.path.join(base_dir, script_path_relative)

    if not os.path.exists(script_path):
        logger.error(f"CRITICAL: Could not find script for {step_name} at: {script_path}")
        return False

    logger.info(f"--- STARTING {step_name}: {script_path_relative} ---")
    start_time = time.time()

    try:
        # Run the script using the same Python interpreter executing this runner
        result = subprocess.run(
            [sys.executable, script_path],
            check=True,  # Raises CalledProcessError if script fails
            text=True,
            capture_output=False # Stream output directly to console
        )
        
        elapsed = time.time() - start_time
        logger.info(f"--- FINISHED {step_name} in {elapsed:.2f}s ---")
        return True

    except subprocess.CalledProcessError as e:
        logger.error(f"!!! FAILED {step_name} (Exit Code: {e.returncode}) !!!")
        return False
    except Exception as e:
        logger.error(f"!!! ERROR executing {step_name}: {e} !!!")
        return False

def main():
    logger.info("Initializing Daily Auction Pipeline...")
    total_start = time.time()

    # 1. Run Step 1: Auction Scraper
    if not run_script("Step 1 (Auctions)", SCRIPTS["Step 1 (Auctions)"]):
        logger.error("Pipeline aborted due to failure in Step 1.")
        sys.exit(1)

    # Short cool-down to ensure file handles are closed and browser is dead
    time.sleep(2)

    # 2. Run Step 2: History Scraper
    if not run_script("Step 2 (Parcel History)", SCRIPTS["Step 2 (Parcel History)"]):
        logger.error("Pipeline aborted due to failure in Step 2.")
        sys.exit(1)

    time.sleep(1)

    # 3. Run Step 3: Verifier
    if not run_script("Step 3 (Verify)", SCRIPTS["Step 3 (Verify)"]):
        logger.error("Pipeline completed with errors in verification.")
        sys.exit(1)

    total_elapsed = time.time() - total_start
    logger.info(f"=== PIPELINE COMPLETE in {total_elapsed/60:.2f} minutes ===")

if __name__ == "__main__":
    main()