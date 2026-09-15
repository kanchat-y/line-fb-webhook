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

# โหลด token จาก env หรือ config
PAGE_ID = "104158371681569"  # ล็อกเพจเดียว

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

def create_draft(text, image_url=None, schedule=None):
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
        "page_id": PAGE_ID
    }
    cal.append(post)
    Path(CALENDAR).write_text(json.dumps(cal, ensure_ascii=False, indent=2), encoding="utf-8")
    return post

def post_to_facebook(text, image_url=None, schedule=None):
    """โพสต์จริงผ่าน Graph API - รองรับทั้ง URL และไฟล์ local"""
    import urllib.request, urllib.parse
    user_token = os.environ.get("META_ACCESS_TOKEN", "")
    if not user_token:
        return {"error": "META_ACCESS_TOKEN not set"}
    try:
        r = json.loads(urllib.request.urlopen(f"https://graph.facebook.com/v23.0/me/accounts?fields=id,access_token&access_token={user_token}").read().decode())
        pt = next(p["access_token"] for p in r["data"] if p["id"] == PAGE_ID)
    except Exception as e:
        return {"error": str(e)}

    # ถ้า image_url เป็นไฟล์ local ให้อัปโหลดแบบไฟล์ตรง (ไม่ผ่าน URL)
    is_local_file = image_url and Path(image_url).exists()
    if is_local_file and not image_url.startswith("http"):
        # local file path เช่น autopost/media/xxx.jpg
        image_url = str(Path(image_url).resolve())

    if is_local_file:
        # อัปโหลดไฟล์ตรง
        import requests
        try:
            with open(image_url, "rb") as f:
                files = {"source": (Path(image_url).name, f, "image/jpeg")}
                data = {"caption": text, "access_token": pt}
                if schedule:
                    data["published"] = "false"
                    data["scheduled_publish_time"] = str(int(schedule.timestamp()))
                resp = requests.post(f"https://graph.facebook.com/v23.0/{PAGE_ID}/photos", data=data, files=files, timeout=30)
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
        endpoint = f"https://graph.facebook.com/v23.0/{PAGE_ID}/photos"
    elif image_url:
        data = urllib.parse.urlencode({"url": image_url, "caption": text, "access_token": pt}).encode()
        endpoint = f"https://graph.facebook.com/v23.0/{PAGE_ID}/photos"
    elif schedule:
        unix = int(schedule.timestamp())
        data = urllib.parse.urlencode({"message": text, "access_token": pt, "published": "false", "scheduled_publish_time": unix}).encode()
        endpoint = f"https://graph.facebook.com/v23.0/{PAGE_ID}/feed"
    else:
        data = urllib.parse.urlencode({"message": text, "access_token": pt}).encode()
        endpoint = f"https://graph.facebook.com/v23.0/{PAGE_ID}/feed"

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

    def improve_caption(text):
        """ช่วยเกลาแคปชันแบบง่าย ไม่ใช้ LLM (ฟรี)"""
        if "#ก๊อดเองแม่ตั้งให้" not in text:
            text += "\n\n#ก๊อดเองแม่ตั้งให้ #เรื่องทั่วไป"
        # เติมอีโมจิถ้าไม่มี
        if not any(c in text for c in ["�", "🔴", "✨", "🏟️"]):
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

        # 1. ถ้าพิมพ์ "ใช่" / "ยืนยัน" / "โพสต์เลย" -> ยืนยันโพสต์ที่รออยู่
        if text in ["ใช่", "ใช่ครับ", "ยืนยัน", "โพสต์เลย", "ตกลง"] and uid in pending_posts:
            pending = pending_posts.pop(uid)
            result = post_to_facebook(pending["text"], pending["image_url"], pending["schedule"])
            create_draft(pending["text"], pending["image_url"], pending["schedule"])
            if "success" in result:
                pid = result["response"].get("id") or result["response"].get("post_id") or ""
                reply = f"✅ โพสต์สำเร็จ!\nhttps://facebook.com/{pid}\nเพจ: ก๊อดเองแม่ตั้งให้"
            else:
                reply = f"❌ โพสต์ไม่สำเร็จ: {result.get('error','')[:300]}"
            line_api.reply_message(event.reply_token, TextMessage(text=reply))
            return

        # 2. ถ้าพิมพ์ "ช่วยเกลา" / "ช่วยคิด" -> ปรับแคปชันที่รออยู่
        if any(k in text for k in ["ช่วยเกลา", "ช่วยคิด", "อยากให้ช่วย"]) and uid in pending_posts:
            pending = pending_posts[uid]
            pending["text"] = improve_caption(pending["text"])
            preview = pending["text"][:300]
            img_note = "📸 มีรูป" if pending["image_url"] else "📝 ไม่มีรูป"
            sched_note = f"⏰ ตั้งเวลา {pending['schedule'].strftime('%d/%m %H:%M')}" if pending["schedule"] else "⚡ โพสต์ทันที"
            reply = f"✨ เกลาแคปชันให้แล้ว:\n---\n{preview}\n---\n{img_note} | {sched_note}\n\nพิมพ์ 'ใช่' เพื่อยืนยันโพสต์ หรือ 'แก้ไข...' เพื่อแก้"
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

        # เก็บเป็น pending รอการยืนยัน (ตามสเปคต้องถามก่อนโพสต์เสมอ)
        pending_posts[uid] = {"text": clean, "image_url": image_url, "schedule": schedule}
        preview = clean[:350]
        img_note = "📸 มีรูปพร้อมโพสต์" if image_url else "📝 ไม่มีรูป (ข้อความล้วน)"
        if schedule:
            sched_note = f"⏰ ตั้งเวลา {schedule.strftime('%d/%m %H:%M น.')} (ต้องล่วงหน้า 10 นาที)"
        else:
            sched_note = "⚡ จะโพสต์ทันที"

        reply = f"📋 Preview ก่อนโพสต์:\n---\n{preview}\n---\n{img_note}\n{sched_note}\n\n✅ พิมพ์ 'ใช่' เพื่อยืนยันโพสต์\n💡 พิมพ์ 'ช่วยเกลา' ให้ช่วยคิดแคปชันเพิ่ม\n✏️ พิมพ์ข้อความใหม่เพื่อแก้ไข"
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
