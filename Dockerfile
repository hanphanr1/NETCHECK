FROM python:3.10-slim

# Cài đặt các dependencies cơ bản
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Thêm key và cài Chrome stable (mới nhất)
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | gpg --dearmor > /etc/apt/trusted.gpg.d/google.gpg \
    && echo "deb [arch=amd64 signed-by=/etc/apt/trusted.gpg.d/google.gpg] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list \
    && apt-get update && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Tải ChromeDriver tương ứng với phiên bản Chrome vừa cài
RUN CHROME_VERSION=$(google-chrome --version | grep -oP '\d+\.\d+\.\d+') \
    && wget -q "https://storage.googleapis.com/chrome-for-testing-public/${CHROME_VERSION}/linux64/chromedriver-linux64.zip" -O /tmp/chromedriver.zip \
    && unzip /tmp/chromedriver.zip -d /tmp \
    && mv /tmp/chromedriver-linux64/chromedriver /usr/local/bin/chromedriver \
    && chmod +x /usr/local/bin/chromedriver \
    && rm -rf /tmp/chromedriver*

# Copy requirements và cài đặt Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy mã nguồn
COPY main.py .

# Biến môi trường cho bot token
ENV BOT_TOKEN=""

# Chạy bot
CMD ["python", "main.py"]