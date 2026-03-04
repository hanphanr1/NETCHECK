FROM python:3.10-slim

# Cai dat dependencies co ban va thu vien cho Chrome
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    curl \
    libnss3 \
    libx11-xcb1 \
    libxcb1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxi6 \
    libxtst6 \
    libxrandr2 \
    libasound2 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    && rm -rf /var/lib/apt/lists/*

# Them key Google va cai Chrome stable (chromedriver co san trong Chrome)
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | gpg --dearmor > /etc/apt/trusted.gpg.d/google.gpg \
    && echo "deb [arch=amd64 signed-by=/etc/apt/trusted.gpg.d/google.gpg] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list \
    && apt-get update && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Selenium se tu dong tai chromedriver

# Copy requirements va cai Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy ma nguon
COPY main.py .

# Bien moi truong cho bot token
ENV BOT_TOKEN=""

# Chay bot
CMD ["python", "main.py"]
