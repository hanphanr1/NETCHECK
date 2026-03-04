FROM python:3.10-slim

# Cài đặt dependencies cơ bản và thư viện cho Chrome/ChromeDriver
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

# Thêm key và cài Chrome stable
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | gpg --dearmor > /etc/apt/trusted.gpg.d/google.gpg \
    && echo "deb [arch=amd64 signed-by=/etc/apt/trusted.gpg.d/google.gpg] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list \
    && apt-get update && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Lấy phiên bản Chrome và tải ChromeDriver tương ứng
RUN set -eux; \
    CHROME_VERSION=$(google-chrome --version | awk '{print $3}' | cut -d '.' -f1-3); \
    echo "Detected Chrome version: $CHROME_VERSION"; \
    wget -q "https://storage.googleapis.com/chrome-for-testing-public/${CHROME_VERSION}/linux64/chromedriver-linux64.zip" -O /tmp/chromedriver.zip; \
    unzip -q /tmp/chromedriver.zip -d /tmp; \
    ls -l /tmp/chromedriver-linux64; \
    mv /tmp/chromedriver-linux64/chromedriver /usr/local/bin/chromedriver; \
    chmod +x /usr/local/bin/chromedriver; \
    rm -rf /tmp/chromedriver*

# Copy requirements và cài đặt Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy mã nguồn
COPY main.py .

# Biến môi trường cho bot token
ENV BOT_TOKEN=""

# Chạy bot
CMD ["python", "main.py"]