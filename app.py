#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LINE -> Facebook AutoPost Webhook
รับไอเดีย+รูปจาก LINE แล้วโพสต์ลงเพจ ก๊อดเองแม่ตั้งให้ (104158371681569)
รองรับ: โพสต์ทันที / ตั้งเวลา

วิธีใช้:
1. สร้าง LINE Official Account ที่ https://developers.line.biz/
2. ตั้ง Webhook URL เป็น https://your-domain/line-webhook
3. ใส่ CHANNEL_SECRET, CHANNEL_ACCESS_TOKEN ใน config.json
4. รัน: python app.py (port 8080)
"""
import os, json, re, pathlib, datetime
from pathlib import Path

# โหลด config
BASE = Path(__file__).parent.parent
CALENDAR = BASE / "calendar.json"
CONFIG = BASE / "config.json"
MEDIA_DIR = BASE / "media"
MEDIA_DIR.mkdir(exist_ok=True)

try:
    from flask import Flask, request, abort
    from linebot import LineBotApi, WebhookHandler
    from linebot.exceptions import InvalidSignatureError
    from linebot.models import MessageEvent, TextMessage, ImageMessage
    HAS_LINE = True
except ImportError:
    HAS_LINE = False
    print("pip install flask line-bot-sdk")

# รองรับหลายเพจ - อ่านจาก config.json + fallback env
# เพจ 104158371681569 (ก๊อดเองแม่ตั้งให้) = token หลัก META_ACCESS_TOKEN (verified 3 เพจ)
# เพจ 788732444316483 (GETUP DEAL) = ต้องใช้ META_ACCESS_TOKEN_GETUPDEAL จาก admin ของเพจนั้น
def _load_pages_from_config():
    try:
        cfg = json.loads(Path(CONFIG).read_text(encoding="utf-8")) if Path(CONFIG).exists() else {}
        pages_list = cfg.get("platforms", {}).get("facebook", {}).get("pages", [])
        if pages_list:
            out = {}
            for p in pages_list:
                out[p["id"]] = {"name": p["name"], "page_token": "", "user_token_env": p.get("token_env", "META_ACCESS_TOKEN")}
            return out
    except: pass
    return None

PAGES = _load_pages_from_config() or {
    "104158371681569": {"name": "ก๊อดเองแม่ตั้งให้", "page_token": "", "user_token_env": "META_ACCESS_TOKEN"},
    "788732444316483": {"name": "GETUP DEAL", "page_token": "EAAOEO2TluZCYBSh4k6cC3axuXama9Kglc6P4E9Cw8KdzDxtko7Ue3OaQQT9BMmx4ilXBmWki1n1GnUbLKDg0FhKCftT4vUcewWNOlG7lBETlbVqmtJmdJKJTn3C92xfrtR4TH4sjnZAWD6jrGbhfDbsLAUHhPfpddtqrfdZArEiSZAht4fxonVQat76o0V1ZCFji1W18m", "user_token_env": "META_ACCESS_TOKEN_GETUPDEAL"}
}
# GETUP DEAL page_token นี้ expires_at=0 (ไม่หมดอายุ) จาก long-lived user token 989815560846326 - อัปเดต 18 Sep 2026
PAGE_ID = "104158371681569"  # ค่าเริ่มต้น
FORCE_PAGE_ID = __import__("os").environ.get("FORCE_PAGE_ID") or __import__("os").environ.get("DEFAULT_PAGE_ID")  # ถ้าตั้งไว้จะล็อคเพจเดียวไม่ถามเลือก
if FORCE_PAGE_ID:
    PAGE_ID = FORCE_PAGE_ID
    print(f"[FORCE] Locked to page {PAGE_ID}")

def load_json(p, default):
    return json.loads(Path(p).read_text(encoding="utf-8")) if Path(p).exists() else default

def parse_schedule(text):
    """หาเวลาจากข้อความ เช่น 'โพสต์ 19:45' 'พรุ่งนี้ 9 โมง' 'ตั้งเวลา 2026-09-16 09:00'"""
    # รูปแบบง่าย: หา HH:MM
    m = re.search(r'(\d{1,2}):(\d{2})', text)
    if m:
        hh, mm = int(m.group(1)), int(m.group(2))
        # ถ้ามีคำว่า พรุ่งนี้
        import datetime
        from datetime import timezone, timedelta
        bkk = timezone(timedelta(hours=7))
        now = datetime.datetime.now(bkk)
        target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if "พรุ่งนี้" in text or target <= now:
            if target <= now:
                target += datetime.timedelta(days=1)
        # ต้องล่วงหน้า 10 นาที
        if (target - now).total_seconds() < 600:
            target += datetime.timedelta(minutes=10)
        return target
    if "พรุ่งนี้" in text:
        import datetime
        from datetime import timezone, timedelta
        bkk = timezone(timedelta(hours=7))
        now = datetime.datetime.now(bkk)
        return (now + datetime.timedelta(days=1)).replace(hour=9, minute=0, second=0)
    return None

def create_draft(text, image_url=None, schedule=None, page_id=None):
    """สร้าง draft ลง calendar.json"""
    cal = load_json(CALENDAR, [])
    new_id = f"post-{len(cal)+1:03d}"
    existing = {p["id"] for p in cal}
    n=1
    while new_id in existing:
        new_id = f"post-{len(cal)+n:03d}"
        n+=1
    from datetime import timezone, timedelta, datetime
    bkk = timezone(timedelta(hours=7))
    post = {
        "id": new_id,
        "platforms": ["facebook"],
        "message": text,
        "status": "scheduled" if schedule else "draft",
        "scheduled_at": schedule.isoformat() if schedule else None,
        "approved": True,  # มาจาก LINE ถือว่าอนุมัติแล้ว
        "media_url": image_url or "",
        "created_at": datetime.now(bkk).isoformat(),
        "source": "LINE",
        "page_id": page_id or PAGE_ID
    }
    cal.append(post)
    Path(CALENDAR).write_text(json.dumps(cal, ensure_ascii=False, indent=2), encoding="utf-8")
    return post

def post_to_facebook(text, image_url=None, schedule=None, page_id=None):
    """โพสต์จริงผ่าน Graph API - รองรับทั้ง URL และไฟล์ local และหลายเพจ"""
    import urllib.request, urllib.parse
    target_page = page_id or PAGE_ID
    page_cfg = PAGES.get(target_page, {})
    # ลองใช้ page_token ที่เก็บไว้ก่อน (สำหรับ GETUP DEAL)
    pt = page_cfg.get("page_token")
    if not pt:
        user_token = os.environ.get(page_cfg.get("user_token_env", "META_ACCESS_TOKEN"), "") or os.environ.get("META_ACCESS_TOKEN", "")
        if not user_token:
            return {"error": "META_ACCESS_TOKEN not set"}
        try:
            r = json.loads(urllib.request.urlopen(f"https://graph.facebook.com/v23.0/me/accounts?fields=id,access_token&access_token={user_token}").read().decode())
            pt = next(p["access_token"] for p in r["data"] if p["id"] == target_page)
        except Exception as e:
            return {"error": str(e)}
    # ถ้า image_url เป็นไฟล์ local ให้อัปโหลดแบบไฟล์ตรง (ไม่ผ่าน URL)
    is_local_file = image_url and Path(image_url).exists()
    if is_local_file and not image_url.startswith("http"):
        image_url = str(Path(image_url).resolve())

    if is_local_file:
        import requests
        try:
            with open(image_url, "rb") as f:
                files = {"source": (Path(image_url).name, f, "image/jpeg")}
                data = {"caption": text, "access_token": pt}
                if schedule:
                    data["published"] = "false"
                    data["scheduled_publish_time"] = str(int(schedule.timestamp()))
                resp = requests.post(f"https://graph.facebook.com/v23.0/{target_page}/photos", data=data, files=files, timeout=30)
                if resp.status_code == 200:
                    return {"success": True, "response": resp.json()}
                else:
                    return {"error": resp.text[:2000]}
        except Exception as e:
            return {"error": str(e)}

    # แบบ URL หรือข้อความล้วน
    if image_url and schedule:
        unix = int(schedule.timestamp())
        data = urllib.parse.urlencode({"url": image_url, "caption": text, "access_token": pt, "published": "false", "scheduled_publish_time": unix}).encode()
        endpoint = f"https://graph.facebook.com/v23.0/{target_page}/photos"
    elif image_url:
        data = urllib.parse.urlencode({"url": image_url, "caption": text, "access_token": pt}).encode()
        endpoint = f"https://graph.facebook.com/v23.0/{target_page}/photos"
    elif schedule:
        unix = int(schedule.timestamp())
        data = urllib.parse.urlencode({"message": text, "access_token": pt, "published": "false", "scheduled_publish_time": unix}).encode()
        endpoint = f"https://graph.facebook.com/v23.0/{target_page}/feed"
    else:
        data = urllib.parse.urlencode({"message": text, "access_token": pt}).encode()
        endpoint = f"https://graph.facebook.com/v23.0/{target_page}/feed"

    try:
        req = urllib.request.Request(endpoint, data=data)
        resp = json.loads(urllib.request.urlopen(req, timeout=30).read().decode())
        return {"success": True, "response": resp}
    except Exception as e:
        try:
            body = e.read().decode()
        except:
            body = str(e)
        return {"error": body}

# Flask app
if HAS_LINE:
    app = Flask(__name__)
    line_secret = os.environ.get("LINE_CHANNEL_SECRET", "")
    line_token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
    handler = WebhookHandler(line_secret) if line_secret else None
    line_api = LineBotApi(line_token) if line_token else None

    # เก็บสถานะรอการยืนยัน
    pending_images = {}  # user_id -> image_url
    pending_posts = {}   # user_id -> {text, image_url, schedule}

    def gemini_expand(short_text):
        """ใช้ Gemini ฟรีขยายไอเดียสั้นๆ เป็นแคปชันยาว 5-7 บรรทัด"""
        import requests
        key = os.environ.get("GEMINI_API_KEY", "")
        if not key:
            return ""
        prompt = f"""ขยายไอเดียสั้นๆ "{short_text}" เป็นแคปชัน Facebook สำหรับเพจ "ก๊อดเองแม่ตั้งให้" (ความบันเทิง/เรื่องทั่วไป)

เงื่อนไข:
- เขียน 5-7 บรรทัด เล่าเรื่องบรรยากาศในรูปให้ชวนฝัน (เช่น sky rooftop ยามค่ำคืน วิวพาโนรามา แสงไฟระยิบระยับ)
- โทน: สนุก เป็นกันเอง ชวนคนมาคอมเมนต์/แชร์รูป ใส่อีโมจิ 1-2 ตัว
- ใส่แฮชแท็ก 3-5 อัน ต้องมี #ก๊อดเองแม่ตั้งให้
- ภาษาไทย สละสลวย ไม่สั้นเกินไป ให้เหมือนตัวอย่าง:
"🌃✨ Sky Rooftop สุดอลังการ วิวหลักล้านที่ต้องไปสักครั้ง! ใครชอบนั่งชิลชมวิวเมืองยามค่ำคืนต้องหลงรัก..."
- อย่าตอบสั้นๆ แค่ 1-2 คำ ต้องขยายให้เต็ม
"""
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent?key={key}"
            r = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=20)
            if r.status_code == 200:
                j = r.json()
                txt = j["candidates"][0]["content"]["parts"][0]["text"]
                return txt.strip()
        except Exception as e:
            print(f"gemini error: {e}")
        return ""

    def gemini_image(prompt_text):
        """สร้างรูป AI ด้วย Pollinations (ฟรี ไม่ต้องใช้ Gemini Image)"""
        try:
            import urllib.parse
            # ใช้ Pollinations ฟรี
            q = urllib.parse.quote(prompt_text[:150])
            return f"https://image.pollinations.ai/prompt/{q}?width=1024&height=1024&nologo=true"
        except:
            return ""

    def improve_caption(text):
        """ช่วยเกลาแคปชัน - ลองใช้ Gemini ก่อน ถ้าไม่ได้ใช้แบบง่าย"""
        expanded = gemini_expand(text)
        if expanded and len(expanded) > 20:
            return expanded
        # fallback แบบง่าย
        if "#ก๊อดเองแม่ตั้งให้" not in text:
            text += "\n\n#ก๊อดเองแม่ตั้งให้ #เรื่องทั่วไป"
        if not any(c in text for c in ["✨", "🔴", "🏟️", "😅", "❤️"]):
            text = "✨ " + text
        return text

    @app.route("/ping", methods=["GET"])
    def ping():
        return "OK", 200

    @app.route("/", methods=["GET"])
    def index():
        return "LINE-FB Webhook running. POST /line-webhook for LINE.", 200

    @app.route("/line-webhook", methods=["POST"])
    def line_webhook():
        sig = request.headers.get("X-Line-Signature", "")
        body = request.get_data(as_text=True)
        try:
            handler.handle(body, sig)
        except InvalidSignatureError:
            abort(400)
        return "OK"

    @handler.add(MessageEvent, message=TextMessage)
    def handle_text(event):
        text = event.message.text.strip()
        uid = event.source.user_id

        # 0. เลือกเพจ (ถ้ารอเลือกเพจอยู่) - บังคับทุกครั้งก่อนโพสต์
        if uid in pending_posts and pending_posts[uid].get("awaiting_page"):
            choice = text.strip().lower()
            if choice in ["1", "1.", "ก๊อด", "ก๊อดเอง", "ก๊อดเองแม่ตั้งให้"]:
                pending_posts[uid]["page_id"] = "104158371681569"
                pending_posts[uid].pop("awaiting_page", None)
                pending_posts[uid]["page_id_selected"] = True
            elif choice in ["2", "2.", "getup", "getup deal", "getupdeal", "getupdeal "]:
                pending_posts[uid]["page_id"] = "788732444316483"
                pending_posts[uid].pop("awaiting_page", None)
                pending_posts[uid]["page_id_selected"] = True
            else:
                line_api.reply_message(event.reply_token, TextMessage(text="❓ เลือกเพจไม่ถูก พิมพ์ 1 สำหรับ ก๊อดเองแม่ตั้งให้ หรือ 2 สำหรับ GETUP DEAL"))
                return
            # หลังเลือกเพจแล้ว ถามยืนยัน
            p = pending_posts[uid]
            pg_name = PAGES.get(p["page_id"], {}).get("name", p["page_id"])
            preview = p["text"][:350] if p["text"] else "(ไม่มีข้อความ)"
            img_note = "📸 มีรูป" if p["image_url"] else "📝 ไม่มีรูป"
            sched_note = f"⏰ ตั้งเวลา {p['schedule'].strftime('%d/%m %H:%M')}" if p["schedule"] else "⚡ โพสต์ทันที"
            reply = f"✅ เลือกเพจ: {pg_name}\n📋 Preview:\n---\n{preview}\n---\n{img_note} | {sched_note}\n\nพิมพ์ 'ใช่' เพื่อยืนยันโพสต์ หรือ 'ช่วยเกลา' ให้ช่วยคิด"
            line_api.reply_message(event.reply_token, TextMessage(text=reply))
            return

        # 1. ถ้าพิมพ์ "ใช่" / "ยืนยัน" / "โพสต์เลย" -> ต้องเลือกเพจก่อนโพสต์เสมอ (ถ้า FORCE_PAGE_ID จะโพสต์เลยไม่ถาม)
        if text in ["ใช่", "ใช่ครับ", "ยืนยัน", "โพสต์เลย", "ตกลง"] and uid in pending_posts:
            if FORCE_PAGE_ID:
                pending_posts[uid]["page_id"] = FORCE_PAGE_ID
                pending_posts[uid]["page_id_selected"] = True
            # บังคับถามเลือกเพจทุกครั้ง (ตามคำขอ) - ข้ามถ้า FORCE
            if not FORCE_PAGE_ID and not pending_posts[uid].get("awaiting_page") and not pending_posts[uid].get("page_id_selected"):
                line_api.reply_message(event.reply_token, TextMessage(text="📌 จะโพสต์ลงเพจไหน?\n1. ก๊อดเองแม่ตั้งให้\n2. GETUP DEAL\n\nพิมพ์ 1 หรือ 2"))
                pending_posts[uid]["awaiting_page"] = True
                return
            if not FORCE_PAGE_ID and pending_posts[uid].get("awaiting_page"):
                line_api.reply_message(event.reply_token, TextMessage(text="📌 กรุณาเลือกเพจก่อน: พิมพ์ 1 (ก๊อดเองแม่ตั้งให้) หรือ 2 (GETUP DEAL)"))
                return
            pending = pending_posts.pop(uid)
            result = post_to_facebook(pending["text"], pending["image_url"], pending["schedule"], pending.get("page_id"))
            create_draft(pending["text"], pending["image_url"], pending["schedule"], pending.get("page_id"))
            pg_name = PAGES.get(pending.get("page_id"), {}).get("name", pending.get("page_id", "ก๊อดเองแม่ตั้งให้"))
            if "success" in result:
                pid = result["response"].get("id") or result["response"].get("post_id") or ""
                reply = f"✅ โพสต์สำเร็จ!\nhttps://facebook.com/{pid}\nเพจ: {pg_name}"
            else:
                reply = f"❌ โพสต์ไม่สำเร็จ ({pg_name}): {result.get('error','')[:300]}"
            line_api.reply_message(event.reply_token, TextMessage(text=reply))
            return

        # 2. ถ้าพิมพ์ "ช่วยเกลา" / "ช่วยคิด" -> ปรับแคปชันที่รออยู่ด้วย Gemini
        if any(k in text for k in ["ช่วยเกลา", "ช่วยคิด", "อยากให้ช่วย"]) and uid in pending_posts:
            pending = pending_posts[uid]
            # ถ้าข้อความสั้นมาก ให้ Gemini ขยาย
            expanded = gemini_expand(pending["text"])
            if expanded:
                pending["text"] = expanded
            else:
                pending["text"] = improve_caption(pending["text"])
            preview = pending["text"][:400]
            img_note = "📸 มีรูป" if pending["image_url"] else "📝 ไม่มีรูป"
            sched_note = f"⏰ ตั้งเวลา {pending['schedule'].strftime('%d/%m %H:%M')}" if pending["schedule"] else "⚡ โพสต์ทันที"
            reply = f"✨ Gemini ช่วยคิดให้แล้ว:\n---\n{preview}\n---\n{img_note} | {sched_note}\n\nพิมพ์ 'ใช่' เพื่อยืนยันโพสต์ หรือ 'แก้ไข...' เพื่อแก้"
            line_api.reply_message(event.reply_token, TextMessage(text=reply))
            return

        # 2.1 ถ้าพิมพ์ "สร้างรูป" / "2" -> สร้างรูป AI
        if text.strip() in ["2", "2.", "สร้างรูป", "ให้ AI สร้างรูป", "สร้างรูปด้วย"] and uid in pending_posts:
            pending = pending_posts[uid]
            prompt = pending["text"][:100] if pending["text"] else "football stadium"
            img_url = gemini_image(prompt)
            pending["image_url"] = img_url
            pending_images.pop(uid, None)
            reply = f"🎨 สร้างรูป AI แล้ว:\n{img_url}\n\n📋 Preview:\n{pending['text'][:300]}\n\nพิมพ์ 'ใช่' เพื่อยืนยันโพสต์พร้อมรูปนี้"
            line_api.reply_message(event.reply_token, TextMessage(text=reply))
            return

        # 3. ข้อความใหม่ - แยกเวลาและทำความสะอาด
        schedule = parse_schedule(text)
        clean = re.sub(r'โพสต์.*|ตั้งเวลา.*|\d{1,2}:\d{2}|พรุ่งนี้', '', text).strip()
        if not clean:
            clean = text

        image_url = pending_images.pop(uid, None)

        # ถ้าไม่มีรูป และไม่มีข้อความชัดเจน ถามเรื่องรูป
        if not image_url and not any(k in text for k in ["โพสต์เลย", "ตั้งเวลา"]) and len(clean) < 5:
            line_api.reply_message(event.reply_token, TextMessage(text="📸 ไม่เห็นรูปแนบ ต้องการใช้รูปอะไร?\n1. ส่งรูปมา\n2. ให้ AI สร้างรูปสนามใหม่\n3. โพสต์แบบข้อความล้วน\n\nพิมพ์เลขหรือส่งรูปมาได้เลย"))
            pending_posts[uid] = {"text": clean, "image_url": None, "schedule": schedule}
            return

        # ถ้า FORCE_PAGE_ID จะล็อคเพจเลยไม่ถาม
        if FORCE_PAGE_ID:
            pending_posts[uid] = {"text": clean, "image_url": image_url, "schedule": schedule, "page_id": FORCE_PAGE_ID, "page_id_selected": True}
        else:
            # ไม่ auto เลือกเพจแล้ว - บังคับถามทุกครั้งก่อนโพสต์
            hint_page = None
            if any(k in text.lower() for k in ["getup", "get up"]):
                hint_page = "788732444316483"
            elif "ก๊อด" in text:
                hint_page = "104158371681569"
            pending_posts[uid] = {"text": clean, "image_url": image_url, "schedule": schedule, "page_id": None, "page_id_selected": False}
            if hint_page:
                pending_posts[uid]["hint_page"] = hint_page
        preview = clean[:350] if clean else "(ไม่มีข้อความ - มีแต่รูป)"
        img_note = "📸 มีรูปพร้อมโพสต์" if image_url else "📝 ไม่มีรูป (ข้อความล้วน)"
        if schedule:
            sched_note = f"⏰ ตั้งเวลา {schedule.strftime('%d/%m %H:%M น.')} (ต้องล่วงหน้า 10 นาที)"
        else:
            sched_note = "⚡ จะโพสต์ทันที"
        if hint_page:
            pg_name = PAGES[hint_page]["name"]
            page_note = f"📄 เพจที่เดาจากข้อความ: {pg_name} (ยังต้องยืนยัน 1/2)"
        else:
            page_note = "📄 เพจ: ยังไม่ได้เลือก (จะให้เลือกตอนพิมพ์ 'ใช่')"

        reply = f"📋 Preview ก่อนโพสต์:\n---\n{preview}\n---\n{img_note} | {sched_note}\n{page_note}\n\n✅ พิมพ์ 'ใช่' เพื่อยืนยันโพสต์\n💡 พิมพ์ 'ช่วยเกลา' ให้ช่วยคิดแคปชันเพิ่ม\n✏️ พิมพ์ข้อความใหม่เพื่อแก้ไข"
        line_api.reply_message(event.reply_token, TextMessage(text=reply))

    @handler.add(MessageEvent, message=ImageMessage)
    def handle_image(event):
        uid = event.source.user_id
        msg_id = event.message.id
        try:
            content = line_api.get_message_content(msg_id)
            img_path = MEDIA_DIR / f"{msg_id}.jpg"
            with open(img_path, "wb") as f:
                for chunk in content.iter_content():
                    f.write(chunk)
            # เก็บไฟล์ local ไว้โพสต์ตรง ไม่ต้องอัป catbox
            local_path = str(img_path)
            pending_images[uid] = local_path
            # ถ้ามี pending text อยู่แล้ว ให้ใส้รูปให้
            if uid in pending_posts and pending_posts[uid].get("text"):
                pending_posts[uid]["image_url"] = local_path
            else:
                pending_posts[uid] = {"text": "", "image_url": local_path, "schedule": None}
            line_api.reply_message(event.reply_token, TextMessage(text=f"📸 รับรูปแล้ว! ✅\nตอนนี้ส่งแคปชันมาได้เลย แล้วบอทจะถาม 'โพสต์เลยหรือตั้งเวลา?' ก่อนโพสต์"))
        except Exception as e:
            print(f"handle_image error: {e}")
            line_api.reply_message(event.reply_token, TextMessage(text=f"❌ รับรูปไม่สำเร็จ: {str(e)[:200]}"))

    if __name__ == "__main__":
        app.run(host="0.0.0.0", port=8080, debug=False, use_reloader=False)
else:
    print("LINE SDK not installed - run: pip install flask line-bot-sdk")
