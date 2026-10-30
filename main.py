from datetime import datetime, timedelta, timezone
import json
import os
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import pandas as pd
import requests

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# ⚠️ ตั้งค่า LINE Token และ Domain ของ Render
LINE_ACCESS_TOKEN = (
    "Kk2/DLOisxDYgvPI2WICBRGy98EN6Ln2+ry2hD57kH45D7BSWPpkrRx5lISwCImSBH8rFBTsC6OoXugT8dBJntGwg2EJbP4oTaY/cIuWX//7YQlgfhNLF2bf4tqdqrBn8eH1whNB0PRoCFHejv4+WAdB04t89/1O/w1cDnyilFU="
)
LINE_USER_ID = "U32ef157628dbd5df9f472662602e882e"
RENDER_URL = "https://it-helpdesk-bot-pepi.onrender.com"

# 🔴 วาง URL ของ Google Apps Script Web App ที่เพิ่ง Deploy ตรงนี้
APPS_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbxT-XO7kF6IccnmB1tj8bmayY3DL--068Ne3dDllSSU_1oFM5xDgnK5h7Ak8ADo5mfyAw/exec"


def call_apps_script(payload):
    try:
        response = requests.post(APPS_SCRIPT_URL, json=payload, timeout=10)
        return response.json()
    except Exception as e:
        print("❌ Apps Script Connection Error:", e)
        return None


def send_line_notification(message):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_ACCESS_TOKEN}",
    }
    payload = {"to": LINE_USER_ID, "messages": [{"type": "text", "text": message}]}
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=5)
        return response.json()
    except Exception as e:
        print("LINE notification error:", e)
        return None


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


# กำหนดโซนเวลาประเทศไทย (UTC+7)
TH_TIMEZONE = timezone(timedelta(hours=7))

@app.post("/submit")
async def submit_form(
    name: str = Form(...),
    department: str = Form(...),
    issue_type: str = Form(...),
    detail: str = Form(...),
):
    # ดึงเวลาปัจจุบันตามโซนเวลาประเทศไทย (UTC+7)
    timestamp = datetime.now(TH_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
    
    payload = {
        "action": "append",
        "timestamp": timestamp,
        "name": name,
        "department": department,
        "issue_type": issue_type,
        "detail": detail,
        "status": "รอดำเนินการ"
    }
    
    result = call_apps_script(payload)
    row_idx = result.get("row") if result and result.get("status") == "success" else None
    
    if row_idx:
        print(f"✅ บันทึกข้อมูลเรียบร้อยแล้วที่แถว {row_idx}")
    else:
        print("⚠️ ไม่สามารถบันทึกข้อมูลลง Google Sheet ได้")

    # สร้างข้อความแจ้งเตือนเข้า LINE
    close_link = f"{RENDER_URL}/close-ticket/{row_idx}" if row_idx else "ไม่สามารถระบุแถวได้"
    
    line_msg = (
        f"🚨 มีงานแจ้งซ่อม IT ใหม่! 🚨\n"
        f"------------------------------\n"
        f"🕒 เวลา: {timestamp}\n"
        f"👤 ผู้แจ้ง: {name} ({department})\n"
        f"🛠 ปัญหา: {issue_type}\n"
        f"📝 รายละเอียด: {detail}\n"
        f"------------------------------\n"
        f"✅ คลิกปิดงานนี้: {close_link}\n"
        f"📊 ดูเคสทั้งหมด: {RENDER_URL}/dashboard"
    )
    send_line_notification(line_msg)

    return RedirectResponse(url="/success", status_code=303)


@app.get("/close-ticket/{row_idx}", response_class=HTMLResponse)
async def close_ticket(request: Request, row_idx: int):
    payload = {
        "action": "close",
        "row_idx": row_idx
    }
    call_apps_script(payload)

    return """
    <!DOCTYPE html>
    <html lang="th">
    <head>
        <meta charset="UTF-8">
        <script src="https://cdn.tailwindcss.com"></script>
        <link href="https://fonts.googleapis.com/css2?family=Prompt:wght@300;400;500;600&display=swap" rel="stylesheet">
        <style>body { font-family: 'Prompt', sans-serif; }</style>
        <title>ปิดงานสำเร็จ</title>
    </head>
    <body class="bg-slate-950 flex items-center justify-center min-h-screen p-4">
        <div class="bg-slate-900 border border-slate-800 p-8 rounded-2xl shadow-xl text-center max-w-md">
            <div class="text-emerald-400 text-6xl mb-4">🎉</div>
            <h2 class="text-2xl font-bold text-white mb-2">ปิดงานสำเร็จแล้ว!</h2>
            <p class="text-slate-300 mb-6">ระบบได้อัปเดตสถานะเคสนี้เป็น "เสร็จสิ้น" เรียบร้อย</p>
            <a href="/dashboard" class="block w-full bg-blue-600 hover:bg-blue-500 text-white font-bold py-3 rounded-xl transition">📊 ไปที่แดชบอร์ด</a>
        </div>
    </body>
    </html>
    """


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    tickets = []
    total_cases = 0
    pending_cases = 0
    finished_cases = 0

    try:
        payload = {"action": "get_all"}
        response = requests.post(APPS_SCRIPT_URL, json=payload, timeout=10)
        rows = response.json()
        
        if rows and len(rows) > 1:
            header = rows[0]
            data_rows = rows[1:]
            
            df = pd.DataFrame(data_rows, columns=["เวลา", "ผู้แจ้ง", "แผนก", "ประเภทปัญหา", "รายละเอียด", "สถานะ"][:len(header)])
            df = df[df["ผู้แจ้ง"].str.strip() != ""]
            total_cases = len(df)
            
            if "สถานะ" in df.columns:
                pending_cases = len(df[df["สถานะ"].str.strip() == "รอดำเนินการ"])
                finished_cases = total_cases - pending_cases

            tickets = df.to_dict(orient="records")
            tickets.reverse()
    except Exception as e:
        print("Dashboard load error:", e)

    html_content = f"""
    <!DOCTYPE html>
    <html lang="th">
    <head>
        <meta charset="UTF-8">
        <script src="https://cdn.tailwindcss.com"></script>
        <link href="https://fonts.googleapis.com/css2?family=Prompt:wght@300;400;500;600;700&display=swap" rel="stylesheet">
        <style>body {{ font-family: 'Prompt', sans-serif; }}</style>
        <title>IT Helpdesk - แดชบอร์ด</title>
    </head>
    <body class="bg-slate-950 text-slate-100 min-h-screen p-6">
        <div class="max-w-[95%] mx-auto space-y-6">
            <div class="flex justify-between items-center bg-slate-900 p-6 rounded-2xl border border-slate-800">
                <h1 class="text-3xl font-bold text-blue-400">📊 IT Helpdesk Command Center</h1>
                <a href="/" class="bg-blue-600 hover:bg-blue-500 text-white px-5 py-2.5 rounded-xl font-bold transition">➕ แจ้งซ่อมเพิ่ม</a>
            </div>
            
            <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div class="bg-slate-900 border border-slate-800 p-6 rounded-2xl">
                    <p class="text-sm text-slate-400 font-bold">เคสทั้งหมด</p>
                    <h3 class="text-4xl font-extrabold text-white mt-1">{total_cases}</h3>
                </div>
                <div class="bg-slate-900 border border-slate-800 p-6 rounded-2xl">
                    <p class="text-sm text-amber-400 font-bold">รอดำเนินการ</p>
                    <h3 class="text-4xl font-extrabold text-amber-400 mt-1">{pending_cases}</h3>
                </div>
                <div class="bg-slate-900 border border-slate-800 p-6 rounded-2xl">
                    <p class="text-sm text-emerald-400 font-bold">เสร็จสิ้นแล้ว</p>
                    <h3 class="text-4xl font-extrabold text-emerald-400 mt-1">{finished_cases}</h3>
                </div>
            </div>

            <div class="bg-slate-900 border border-slate-800 p-6 rounded-2xl">
                <h2 class="text-xl font-bold mb-4">📋 รายการแจ้งซ่อมล่าสุด</h2>
                <div class="overflow-x-auto">
                    <table class="w-full text-left border-collapse">
                        <thead>
                            <tr class="bg-slate-800 text-slate-300 text-sm">
                                <th class="p-3">เวลา</th>
                                <th class="p-3">ผู้แจ้ง</th>
                                <th class="p-3">แผนก</th>
                                <th class="p-3">ประเภทปัญหา</th>
                                <th class="p-3">รายละเอียด</th>
                                <th class="p-3 text-center">สถานะ</th>
                            </tr>
                        </thead>
                        <tbody class="divide-y divide-slate-800 text-sm">
    """

    if not tickets:
        html_content += (
            '<tr><td colspan="6" class="p-6 text-center text-slate-500">ยังไม่มีประวัติการแจ้งซ่อม</td></tr>'
        )
    else:
        for t in tickets:
            status_text = t.get("สถานะ", "").strip()
            status_badge = (
                '<span class="bg-amber-500/10 text-amber-400 px-3 py-1 rounded-full font-bold">รอดำเนินการ</span>'
                if status_text == "รอดำเนินการ"
                else f'<span class="bg-emerald-500/10 text-emerald-400 px-3 py-1 rounded-full font-bold">{status_text or "เสร็จสิ้น"}</span>'
            )
            html_content += f"""
                <tr class="hover:bg-slate-800/50">
                    <td class="p-3 text-slate-400">{t.get('เวลา', '')}</td>
                    <td class="p-3 font-bold">{t.get('ผู้แจ้ง', '')}</td>
                    <td class="p-3">{t.get('แผนก', '')}</td>
                    <td class="p-3">{t.get('ประเภทปัญหา', '')}</td>
                    <td class="p-3 text-slate-300">{t.get('รายละเอียด', '')}</td>
                    <td class="p-3 text-center">{status_badge}</td>
                </tr>
            """

    html_content += """
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    return html_content


@app.get("/success", response_class=HTMLResponse)
async def success(request: Request):
    return """
    <!DOCTYPE html>
    <html lang="th">
    <head>
        <meta charset="UTF-8">
        <script src="https://cdn.tailwindcss.com"></script>
        <link href="https://fonts.googleapis.com/css2?family=Prompt:wght@300;400;500;600&display=swap" rel="stylesheet">
        <style>body { font-family: 'Prompt', sans-serif; }</style>
    </head>
    <body class="bg-slate-950 flex items-center justify-center min-h-screen p-4">
        <div class="bg-slate-900 border border-slate-800 p-8 rounded-2xl shadow-xl text-center max-w-md">
            <div class="text-emerald-400 text-6xl mb-4">✅</div>
            <h2 class="text-2xl font-bold text-white mb-2">ส่งเรื่องสำเร็จแล้ว!</h2>
            <p class="text-slate-300 mb-6">ระบบได้บันทึกข้อมูลและแจ้งเตือนไปที่ทีม IT เรียบร้อย</p>
            <div class="space-y-3">
                <a href="/" class="block w-full bg-blue-600 hover:bg-blue-500 text-white font-bold py-3 rounded-xl transition">แจ้งปัญหาอื่นเพิ่ม</a>
                <a href="/dashboard" class="block w-full bg-slate-800 hover:bg-slate-700 text-slate-200 font-bold py-3 rounded-xl transition">📊 ดูสถานะเคสทั้งหมด</a>
            </div>
        </div>
    </body>
    </html>
    """