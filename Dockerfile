FROM python:3.10-slim

# Cài đặt dependencies cơ bản
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements và cài Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy mã nguồn
COPY main.py .

# Biến môi trường cho bot token
ENV BOT_TOKEN=""

# Chạy bot
CMD ["python", "main.py"]