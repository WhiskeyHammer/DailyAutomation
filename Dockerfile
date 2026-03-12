FROM python:3.10-slim

# 1. Install Chromium and dependencies + increase shared memory
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# Create a larger /dev/shm (default is often 64MB, Chrome needs more)
RUN mkdir -p /dev/shm && chmod 1777 /dev/shm

# 2. Set up the working directory
WORKDIR /app

# 3. Copy files and install Python libraries
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY browser_config.py .
COPY sam_contracts/ sam_contracts/
COPY junkyard_scraper/ junkyard_scraper/

# 4. Command to run the app
CMD ["python", "main.py"]