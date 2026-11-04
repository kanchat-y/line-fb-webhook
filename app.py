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
    from linebot.models import MessageEvent, TextMessage, ImageMessage, VideoMessage, LocationMessage
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

# ==== โลเคชั่น: รับพิกัดจาก LIFF / LINE แล้วแนบลงแคปชันตอนโพสต์ ====
# รูปแบบข้อความจากหน้า LIFF: "LOCATION 13.756300,100.501800"
LOCATION_CMD_RE = re.compile(r"^LOCATION\s+(-?\d{1,3}(?:\.\d+)?)\s*,\s*(-?\d{1,3}(?:\.\d+)?)\s*$", re.IGNORECASE)
# แบบที่ผู้ใช้คัดลอกพิกัดมาวางเอง (ต้องมีทศนิยม 4 หลักขึ้นไป กันแคปชันธรรมดาโดนเข้าใจผิด)
LOCATION_LOOSE_RE = re.compile(r"^\s*(-?\d{1,3}\.\d{4,})\s*,\s*(-?\d{1,3}\.\d{4,})\s*$")


def valid_coords(lat, lng):
    """เช็คว่าพิกัดอยู่ในช่วงที่ถูกต้อง"""
    try:
        lat, lng = float(lat), float(lng)
    except (TypeError, ValueError):
        return False
    return -90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0


def maps_url(lat, lng):
    """สร้างลิงก์ Google Maps (ไม่ต้องใช้ API key)"""
    return f"https://www.google.com/maps?q={float(lat):.6f},{float(lng):.6f}"


def parse_location_text(text):
    """เจอพิกัดในข้อความไหม -> (lat, lng) หรือ None"""
    if not text:
        return None
    m = LOCATION_CMD_RE.match(text.strip()) or LOCATION_LOOSE_RE.match(text.strip())
    if not m:
        return None
    try:
        lat, lng = float(m.group(1)), float(m.group(2))
    except (TypeError, ValueError):
        return None
    return (lat, lng) if valid_coords(lat, lng) else None


def apply_location(text, loc):
    """ต่อท้ายลิงก์โลเคชั่นให้แคปชัน (คืนข้อความเดิมถ้าไม่มี loc หรือมีลิงก์แล้ว)"""
    if not loc or not valid_coords(loc.get("lat"), loc.get("lng")):
        return text if text is not None else ""
    label = os.environ.get("LOCATION_LABEL", "📍 ตำแหน่งปัจจุบัน").strip() or "📍 ตำแหน่งปัจจุบัน"
    url = maps_url(loc['lat'], loc['lng'])
    base = (text or "").strip()
    if url in base:
        return base  # มีลิงก์โลเคชั่นนี้อยู่แล้ว (แนบไปตอนคิดแคปชันแล้ว) — ไม่แนบซ้ำ
    block = f"{label}\n{url}"
    return f"{base}\n\n{block}" if base else block


def create_draft(text, image_url=None, schedule=None, page_id=None, images=None, videos=None):
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
        "media_urls": list(images or []) or ([image_url] if image_url else []),
        "video_urls": list(videos or []),
        "created_at": datetime.now(bkk).isoformat(),
        "source": "LINE",
        "page_id": page_id or PAGE_ID
    }
    cal.append(post)
    Path(CALENDAR).write_text(json.dumps(cal, ensure_ascii=False, indent=2), encoding="utf-8")
    return post

def post_to_facebook(text, image_url=None, schedule=None, page_id=None, images=None, videos=None):
    """โพสต์จริงผ่าน Graph API - รองรับรูปเดียว/หลายรูป/วิดีโอ ทั้ง URL และไฟล์ local และหลายเพจ"""
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
    imgs = list(images or []) or ([image_url] if image_url else [])
    vids = list(videos or [])
    if vids:
        return _post_video(target_page, pt, text, vids[0], schedule)
    if len(imgs) > 1:
        return _post_album(target_page, pt, text, imgs, schedule)
    image_url = imgs[0] if imgs else None
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

def _post_video(page_id, pt, text, video_path, schedule=None):
    """อัปโหลดวิดีโอ 1 ไฟล์ (local หรือ URL) พร้อมแคปชัน"""
    import urllib.request, urllib.parse
    is_local = bool(video_path) and not video_path.startswith("http") and Path(video_path).exists()
    try:
        if is_local:
            import requests
            with open(video_path, "rb") as f:
                data = {"description": text or "", "access_token": pt}
                if schedule:
                    data["published"] = "false"
                    data["scheduled_publish_time"] = str(int(schedule.timestamp()))
                resp = requests.post(f"https://graph.facebook.com/v23.0/{page_id}/videos",
                                     data=data, files={"source": (Path(video_path).name, f, "video/mp4")}, timeout=180)
            if resp.status_code == 200:
                return {"success": True, "response": resp.json()}
            return {"error": resp.text[:2000]}
        params = {"file_url": video_path, "description": text or "", "access_token": pt}
        if schedule:
            params.update({"published": "false", "scheduled_publish_time": str(int(schedule.timestamp()))})
        data = urllib.parse.urlencode(params).encode()
        req = urllib.request.Request(f"https://graph.facebook.com/v23.0/{page_id}/videos", data=data)
        resp = json.loads(urllib.request.urlopen(req, timeout=180).read().decode())
        return {"success": True, "response": resp}
    except Exception as e:
        try:
            body = e.read().decode()
        except:
            body = str(e)
        return {"error": body[:2000]}

def _post_album(page_id, pt, text, img_list, schedule=None):
    """โพสต์หลายรูป: อัปโหลดแบบ unpublished ทีละรูป แล้วรวมเป็นโพสต์เดียว"""
    import urllib.request, urllib.parse
    fbids = []
    for img_path in img_list:
        try:
            is_local = bool(img_path) and not img_path.startswith("http") and Path(img_path).exists()
            if is_local:
                import requests
                with open(img_path, "rb") as f:
                    resp = requests.post(f"https://graph.facebook.com/v23.0/{page_id}/photos",
                                         data={"caption": text or "", "access_token": pt, "published": "false"},
                                         files={"source": (Path(img_path).name, f, "image/jpeg")}, timeout=60)
                if resp.status_code != 200:
                    return {"error": f"อัปโหลดรูปไม่สำเร็จ: {resp.text[:500]}"}
                fbids.append(resp.json().get("id"))
            else:
                data = urllib.parse.urlencode({"url": img_path, "caption": text or "", "access_token": pt, "published": "false"}).encode()
                req = urllib.request.Request(f"https://graph.facebook.com/v23.0/{page_id}/photos", data=data)
                fbids.append(json.loads(urllib.request.urlopen(req, timeout=60).read().decode()).get("id"))
        except Exception as e:
            try:
                body = e.read().decode()
            except:
                body = str(e)
            return {"error": body[:1000]}
    try:
        payload = {"message": text or "", "access_token": pt}
        for i, fid in enumerate(fbids):
            payload[f"attached_media[{i}]"] = json.dumps({"media_fbid": fid})
        if schedule:
            payload["published"] = "false"
            payload["scheduled_publish_time"] = str(int(schedule.timestamp()))
        data = urllib.parse.urlencode(payload).encode()
        req = urllib.request.Request(f"https://graph.facebook.com/v23.0/{page_id}/feed", data=data)
        resp = json.loads(urllib.request.urlopen(req, timeout=30).read().decode())
        return {"success": True, "response": resp}
    except Exception as e:
        try:
            body = e.read().decode()
        except:
            body = str(e)
        return {"error": body[:2000]}

RICHMENU_MAIN_ID = os.environ.get("RICHMENU_MAIN_ID", "richmenu-8d538df75d627fed1d5af428130b2232")

def link_richmenu_to_user(user_id, menu_id):
    """เด้ง Rich Menu รายคนกลับหน้าหลักหลังเลือกเพจ (เงียบถ้าไม่สำเร็จ)"""
    import urllib.request
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
    if not token or not menu_id or not user_id:
        return
    try:
        req = urllib.request.Request(
            f"https://api.line.me/v2/bot/user/{user_id}/richmenu/{menu_id}",
            method="POST")
        req.add_header("Authorization", "Bearer " + token)
        urllib.request.urlopen(req, data=b"", timeout=10).read()
    except Exception as e:
        print(f"link_richmenu skip: {e}")

# Flask app
if HAS_LINE:
    app = Flask(__name__)
    line_secret = os.environ.get("LINE_CHANNEL_SECRET", "")
    line_token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
    handler = WebhookHandler(line_secret) if line_secret else None
    line_api = LineBotApi(line_token) if line_token else None

    # เก็บสถานะรอการยืนยัน (รองรับหลายรูป + วิดีโอ)
    pending_images = {}  # user_id -> [image_path, ...] (ไฟล์ที่ยังไม่ได้ผูก draft)
    pending_videos = {}  # user_id -> [video_path, ...]
    pending_posts = {}   # user_id -> {text, images:[...], videos:[...], image_url(รูปแรก), schedule, ...}
    user_location = {}   # user_id -> {lat, lng, src} (พิกัดที่จะแนบลงแคปชัน อยู่จนกว่าผู้ใช้สั่งปิด)
    ai_caption_busy = set()  # user_id ที่กำลังให้ AI เขียนแคปชันอยู่ (กัน webhook retry ทำงานซ้ำ)

    def _imgs(p):
        return p.get("images") or ([p["image_url"]] if p.get("image_url") else [])

    def _vids(p):
        return p.get("videos") or []

    def _sync_first(p):
        imgs = _imgs(p)
        p["images"] = imgs
        p["videos"] = _vids(p)
        p["image_url"] = imgs[0] if imgs else None

    def _media_note(p):
        n, m = len(_imgs(p)), len(_vids(p))
        if n == 0 and m == 0:
            return "📝 ไม่มีรูป (ข้อความล้วน)"
        if n == 1 and m == 0:
            return "📸 มีรูปพร้อมโพสต์"
        parts = []
        if n:
            parts.append(f"📸 {n} รูป")
        if m:
            parts.append(f"🎬 {m} วิดีโอ")
        return " ".join(parts)

    class _RawMessage:
        """ห่อ dict เป็น message object ให้ LineBotApi.reply_message (เรียก .as_json_dict) ส่งได้"""
        def __init__(self, payload):
            self._payload = payload
        def as_json_dict(self):
            return self._payload

    def _apply_page(uid, pid, event):
        """เลือกเพจให้ draft (เรียกได้ทุกจังหวะ) + เด้งเมนูกลับหน้าหลัก + โชว์ preview"""
        p = pending_posts[uid]
        p["page_id"] = pid
        p["page_id_selected"] = True
        p.pop("awaiting_page", None)
        link_richmenu_to_user(uid, RICHMENU_MAIN_ID)
        pg_name = PAGES.get(pid, {}).get("name", pid)
        preview = (p.get("text") or "(ไม่มีข้อความ)")[:350]
        sched = f"⏰ ตั้งเวลา {p['schedule'].strftime('%d/%m %H:%M')}" if p.get("schedule") else "⚡ โพสต์ทันที"
        line_api.reply_message(event.reply_token, TextMessage(text=f"✅ เลือกเพจ: {pg_name}\n📋 Preview:\n---\n{preview}\n---\n{_media_note(p)} | {sched}\n\nกดปุ่ม 'โพสต์' จากเมนูเพื่อยืนยันโพสต์ (หรือพิมพ์ 'ใช่')"))

    def _page_choice_message(text="📌 จะโพสต์ลงเพจไหน?\n1. ก๊อดเองแม่ตั้งให้\n2. GETUP DEAL\n\nกดเลือกที่เมนูได้เลย"):
        """ข้อความถามเพจแบบเดียวทุกจุด: แตะปุ่ม / แตะหน้าเมนู / พิมพ์ 1-2 (เข้าที่เดียวกัน)"""
        from linebot.v3.messaging import TextMessage as V3Text, QuickReply as V3QR, QuickReplyItem as V3Item, MessageAction as V3Act
        payload = V3Text(text=text, quick_reply=V3QR(items=[
            V3Item(action=V3Act(label="ก๊อดเองแม่ตั้งให้", text="1")),
            V3Item(action=V3Act(label="GETUP DEAL", text="2")),
        ])).to_dict()
        return _RawMessage(payload)

    def _loc_note(uid):
        """บรรทัดบอกว่ามีโลเคชั่นจะถูกแนบ (ใช้เติมท้าย preview)"""
        cur = user_location.get(uid)
        if not cur:
            return ""
        return f"\n📍 โลเคชั่นที่จะแนบ: {maps_url(cur['lat'], cur['lng'])}"

    def _set_location(event, lat, lng, src):
        """บันทึกพิกัดของผู้ใช้ + ตอบกลับพร้อมลิงก์"""
        uid = event.source.user_id
        if not valid_coords(lat, lng):
            line_api.reply_message(event.reply_token, TextMessage(text="❌ ค่าพิกัดไม่ถูกต้อง (นอกช่วง lat/lng)"))
            return
        user_location[uid] = {"lat": float(lat), "lng": float(lng), "src": src}
        src_txt = "หน้า location (LIFF)" if src == "liff" else "การแชร์ตำแหน่งใน LINE"
        url = maps_url(lat, lng)
        p = pending_posts.get(uid)
        extra = ""
        if p is not None and (p.get("text") or _imgs(p) or _vids(p)):
            preview = (p.get("text") or "(ไม่มีข้อความ)")[:300]
            extra = f"\n\n📋 Preview ปัจจุบัน:\n---\n{preview}\n---\n{_media_note(p)}"
        line_api.reply_message(event.reply_token, TextMessage(
            text=f"📍 บันทึกโลเคชั่นแล้ว ({src_txt})\nพิกัด: {float(lat):.6f}, {float(lng):.6f}\n{url}"
                 f"\n\n✅ จะแนบลงท้ายแคปชันอัตโนมัติตอนกด 'โพสต์'{extra}"
                 f"\n(พิมพ์ 'ปิด location' เพื่อเลิกแนบ)"))

    def _location_help(event):
        """ตอบเมื่อผู้ใช้พิมพ์ location"""
        uid = event.source.user_id
        cur = user_location.get(uid)
        if cur:
            line_api.reply_message(event.reply_token, TextMessage(
                text=f"📍 โลเคชั่นปัจจุบัน: {float(cur['lat']):.6f}, {float(cur['lng']):.6f}\n{maps_url(cur['lat'], cur['lng'])}"
                     f"\n✅ จะแนบลงแคปชันตอนกด 'โพสต์'\n\n• พิมพ์ 'ปิด location' = เลิกแนบ\n• กดปุ่ม 📍 location ที่เมนู = อัปเดตพิกัดใหม่"))
            return
        line_api.reply_message(event.reply_token, TextMessage(
            text="📍 ยังไม่มีโลเคชั่นสำหรับแนบ\n\nวิธีตั้ง:\n"
                 "1️⃣ กดปุ่ม 📍 location ที่ Rich Menu → หน้าเว็บจะดึงตำแหน่งเครื่องให้ (ต้องตั้ง LIFF_ID ก่อน)\n"
                 "2️⃣ หรือแชร์ตำแหน่งจาก LINE: แตะปุ่ม 📍 ข้างช่องพิมพ์ → เลือกตำแหน่งของคุณ\n"
                 "3️⃣ หรือพิมพ์เอง: LOCATION 13.756300,100.501800"))

    def _do_ai_caption(uid, event):
        """คิดแคปชันจากรูปใน draft ด้วย Gemini (vision) แล้วใส่กลับเป็นข้อความ"""
        if uid in ai_caption_busy:
            try:
                line_api.push_message(uid, TextMessage(text="⏳ กำลังเขียนแคปชันอยู่ — รอสักครู่นะ"))
            except Exception as e:
                print(f"ai_caption busy push error: {e}")
            return
        p = pending_posts.get(uid)
        imgs = _imgs(p) if p else []
        if not imgs:
            imgs = list(pending_images.get(uid, []))
        if not imgs:
            line_api.reply_message(event.reply_token, TextMessage(
                text="📷 ยังไม่มีรูปให้ AI ดู\nส่งรูปก่อน แล้วพิมพ์ 'คิดแคปชั่น' (หรือกดปุ่มที่เมนู)"))
            return
        if not os.environ.get("GEMINI_API_KEY", "").strip():
            line_api.reply_message(event.reply_token, TextMessage(
                text="🔑 ยังไม่ได้ตั้งค่า GEMINI_API_KEY บน Render\nตั้งค่าก่อนจึงจะใช้ AI คิดแคปชันได้ (ยังพิมพ์แคปชันเองได้ตามปกติ)"))
            return
        hint = (p.get("text") or "").strip()[:150] if p else ""
        # reply_token ใช้ได้ครั้งเดียว -> ตอบ "⏳" ด้วย reply แล้วส่งผลลัพธ์ด้วย push
        try:
            line_api.reply_message(event.reply_token, TextMessage(text="⏳ AI กำลังดูรูปแล้วเขียนแคปชัน..."))
        except Exception as e:
            print(f"ai_caption reply skip: {e}")
        # ทำงานในเธรด -> webhook ตอบ LINE ทันที (กัน LINE retry ส่ง event ซ้ำ)
        ai_caption_busy.add(uid)

        def _run():
            try:
                _do_ai_caption_work(uid, imgs, hint, p)
            except Exception as e:
                print(f"ai_caption thread error: {e}")
                try:
                    line_api.push_message(uid, TextMessage(text=f"❌ คิดแคปชันไม่สำเร็จ: {str(e)[:150]}"))
                except Exception as e2:
                    print(f"ai_caption error push fail: {e2}")
            finally:
                ai_caption_busy.discard(uid)

        import threading
        threading.Thread(target=_run, daemon=True).start()

    def _do_ai_caption_work(uid, imgs, hint, p):
        def _push(msg):
            try:
                line_api.push_message(uid, TextMessage(text=msg))
            except Exception as e:
                print(f"ai_caption push error: {e}")

        caption, err = gemini_caption_from_images(imgs[:4], hint)
        if not caption:
            msg = {
                "no_key": "🔑 ยังไม่ได้ตั้งค่า GEMINI_API_KEY บน Render",
                "no_image": "❌ อ่านรูปไม่ได้ (ไฟล์หายหรือใหญ่เกินไป) — ส่งรูปใหม่อีกครั้ง",
                "quota": "🚫 ใช้ AI ครบโควตาฟรีวันนี้แล้ว (จำกัด ~20 ครั้ง/วัน)\nลองใหม่พรุ่งนี้ หรือพิมพ์แคปชันเองได้เลย",
                "api_error": "❌ AI ยังตอบไม่ได้ชั่วคราว (server ยุ่ง) — รอสักครู่แล้วพิมพ์ 'คิดแคปชั่น' อีกครั้ง",
            }.get(err, "❌ AI ตอบกลับไม่สำเร็จชั่วคราว — ลองพิมพ์ 'คิดแคปชั่น' อีกครั้ง หรือพิมพ์แคปชันเอง")
            _push(msg)
            return
        if p is None:
            p = pending_posts[uid] = {"text": "", "images": [], "videos": [], "image_url": None, "schedule": None}
        for fp in pending_images.pop(uid, []):
            if fp not in p.setdefault("images", []):
                p["images"].append(fp)
        # แนบลิงก์ Maps ต่อท้ายแคปชันทันที ถ้าผู้ใช้ตั้งโลเคชั่นไว้ (ตอนโพสต์ apply_location จะไม่แนบซ้ำ)
        p["text"] = apply_location(caption, user_location.get(uid))
        _sync_first(p)
        preview = p["text"][:600]
        _push(
            f"✨ AI เขียนแคปชันจากภาพให้แล้ว ({len(imgs[:4])} รูป):\n---\n{preview}\n---\n"
            f"{_media_note(p)} | ⚡ โพสต์ทันที{_loc_note(uid)}\n\n"
            f"✅ กด 'โพสต์' จากเมนูเพื่อโพสต์เลย หรือพิมพ์ข้อความใหม่เพื่อแก้")

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

    def _image_inline(path, max_bytes=6_000_000):
        """อ่านรูป (local หรือ http) คืน inline_data สำหรับ Gemini — คืน None ถ้าอ่านไม่ได้"""
        import base64
        data, mime = None, "image/jpeg"
        try:
            if str(path).startswith("http"):
                import urllib.request
                with urllib.request.urlopen(str(path), timeout=20) as r:
                    mime = (r.headers.get("Content-Type", "image/jpeg") or "image/jpeg").split(";")[0].strip()
                    data = r.read(max_bytes + 1)
            else:
                if not Path(str(path)).exists():
                    return None
                data = Path(str(path)).read_bytes()
        except Exception as e:
            print(f"inline read skip: {path} -> {e}")
            return None
        if not data:
            return None
        # ถ้ามี PIL ให้ย่อรูป (ลดเวลาอัปโหลด) — ไม่มีก็ใช้ไฟล์เดิม
        try:
            from PIL import Image
            import io
            im = Image.open(io.BytesIO(data)).convert("RGB")
            if max(im.size) > 1600:
                im.thumbnail((1600, 1600))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=82)
            data, mime = buf.getvalue(), "image/jpeg"
        except ImportError:
            if len(data) > max_bytes:
                print(f"inline skip (ใหญ่เกิน {max_bytes} bytes ไม่มี PIL ย่อ): {path}")
                return None
        except Exception as e:
            print(f"inline resize skip: {e}")
        if not data:
            return None
        return {"mime_type": mime, "data": base64.b64encode(data).decode("ascii")}

    def gemini_caption_from_images(image_paths, hint=""):
        """คิดแคปชันภาษาไทยจากรูปด้วย Gemini free tier (vision) -> (caption, err)"""
        key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not key:
            return "", "no_key"
        parts, n_ok = [], 0
        for ip in (image_paths or [])[:4]:
            inl = _image_inline(ip)
            if inl:
                parts.append({"inline_data": inl})
                n_ok += 1
        if not n_ok:
            return "", "no_image"
        model = os.environ.get("GEMINI_VISION_MODEL", "").strip() or "gemini-3.6-flash"
        target_page = PAGES.get(FORCE_PAGE_ID or PAGE_ID, {}).get("name", "") or "ของเพจ"
        hint_line = f"- คำใบ้/หัวข้อจากผู้ใช้: {hint}\n" if hint else ""
        page_tag = str(target_page).replace(" ", "")
        prompt = (
            f"ดูภาพที่แนบมา {n_ok} รูป แล้วเขียนแคปชันภาษาไทยสำหรับโพสต์ Facebook ของเพจ \"{target_page}\"\n"
            "กติกา:\n"
            "- ยาว 3-5 บรรทัด: ขึ้นบรรทัดใหม่ระหว่างแต่ละประโยคให้เห็นชัด (นับแถวแฮชแท็กเป็นบรรทัดด้วย) เล่าสิ่งที่เห็นในภาพจริง (จุดเด่น บรรยากาศ รายละเอียด) ให้สัมพันธ์กับรูป ปิดด้วยคำถามชวนคุย\n"
            "- โทนเป็นกันเอง สนุก ชวนคอมเมนต์/แชร์ ใส่อีโมจิ 1-2 ตัว\n"
            "- ท้ายแคปชันใส่แฮชแท็ก 4-6 อันที่คนน่าจะค้นหาจริง เกี่ยวกับเนื้อหาในรูป (SEO) เช่น สถานที่/สิ่งของ/กิจกรรม/อารมณ์ที่เห็นในภาพ"
            + (f" ต้องมี #{page_tag}" if page_tag != "ของเพจ" else "") + "\n"
            f"{hint_line}"
            "- ตอบเป็นแคปชันอย่างเดียว ไม่ต้องมีคำบรรยายเสริม ไม่ต้องขึ้นต้นว่า \"แคปชัน:\" ไม่ต้องใส่ขีดคั่นครอบ ไม่ต้องใส่ลิงก์"
        )
        payload = json.dumps({"contents": [{"parts": parts + [{"text": prompt}]}]}, ensure_ascii=False)
        import urllib.request, urllib.error
        # โมเดลสำรอง: โควตาฟรีจำกัด ~20 ครั้ง/วัน/โมเดล — ถ้าเต็ม/โหลดหนัก ข้ามไปโมเดลถัดไป
        chain = [model]
        for alt in ("gemini-3.6-flash", "gemini-flash-latest", "gemini-3.5-flash-lite",
                    "gemini-flash-lite-latest", "gemini-3.1-flash-lite"):
            if alt not in chain:
                chain.append(alt)
        last_err, saw_quota = "", False
        j = None
        # จำกัดเวลาทั้งหมด ~75 วิ กัน webhook ค้าง (retry สั้น ๆ 2 ครั้ง/โมเดล)
        import time
        deadline = time.time() + 75
        for mdl in chain:
            if time.time() > deadline:
                break
            for attempt in range(2):
                if time.time() > deadline:
                    break
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{mdl}:generateContent?key={key}"
                try:
                    req = urllib.request.Request(url, data=payload.encode("utf-8"), method="POST")
                    req.add_header("Content-Type", "application/json")
                    with urllib.request.urlopen(req, timeout=25) as r:
                        j = json.loads(r.read().decode("utf-8"))
                    last_err = ""
                    break
                except urllib.error.HTTPError as e:
                    try:
                        last_err = f"{mdl} HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:200]}"
                    except Exception:
                        last_err = f"{mdl} HTTP {e.code}"
                    print(f"gemini_caption {last_err}")
                    if e.code == 429:
                        saw_quota = True
                        break  # โควตาเต็ม -> ข้ามไปโมเดลถัดไปเลย ไม่ retry
                    if e.code in (400, 403, 404):
                        break  # โมเดลใช้ไม่ได้ -> ข้าม
                    time.sleep(1.5)  # 503/5xx -> retry สั้น ๆ
                except Exception as e:
                    last_err = f"{mdl} {type(e).__name__}: {str(e)[:150]}"
                    print(f"gemini_caption {last_err}")
                    time.sleep(1.5)
            else:
                continue
            if not last_err:
                break  # สำเร็จ
        if last_err or not j:
            print(f"gemini_caption give up: {last_err}")
            return "", "quota" if saw_quota else "api_error"
        try:
            parts_out = j["candidates"][0]["content"]["parts"]
            txt = next((p.get("text", "").strip() for p in parts_out if p.get("text")), "")
        except Exception as e:
            print(f"gemini_caption parse error: {e} -> {str(j)[:300]}")
            return "", "bad_response"
        if not txt:
            return "", "bad_response"
        return txt, ""

    @app.route("/ping", methods=["GET"])
    def ping():
        return "OK", 200

    @app.route("/", methods=["GET"])
    def index():
        return "LINE-FB Webhook running. POST /line-webhook for LINE.", 200

    # หน้าเว็บ LIFF สำหรับปุ่ม location (เปิดจาก Rich Menu -> ดึง GPS เครื่อง -> ส่งพิกัดกลับแชท)
    LIFF_HTML = """<!doctype html>
<html lang="th">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>📍 ระบุตำแหน่ง</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
  body { margin:0; min-height:100vh; background:#0B0B0D; color:#F5F0E1;
         font-family:-apple-system,BlinkMacSystemFont,"Noto Sans Thai","Leelawadee UI",Tahoma,sans-serif;
         display:flex; align-items:center; justify-content:center; padding:18px; }
  .card { width:100%; max-width:460px; background:#121215; border:1px solid #C9A227;
          border-radius:16px; padding:22px 18px 24px; text-align:center; }
  h1 { margin:4px 0 12px; font-size:21px; color:#C9A227; }
  #status { margin:8px 0; min-height:26px; font-size:15px; line-height:1.7; }
  .coords { font-family:ui-monospace,SFMono-Regular,Consolas,monospace; font-size:15px;
            background:#1A1A1E; border:1px solid #2C2C31; border-radius:10px; padding:10px 8px;
            color:#F5F0E1; word-break:break-all; }
  .maplink { display:inline-block; margin-top:10px; color:#C9A227; font-size:15px; }
  button { display:block; width:100%; margin-top:14px; padding:15px 12px; font-size:17px; font-weight:700;
           border:0; border-radius:10px; background:#C9A227; color:#0B0B0D; }
  button.secondary { background:#1C1C21; color:#F5F0E1; border:1px solid #3A3A40; font-weight:600; font-size:15px; }
  button:disabled { opacity:.55; }
  .err { margin-top:12px; background:#2A1416; color:#FF9B9B; border:1px solid #5A2A2E;
         border-radius:10px; padding:10px; font-size:14px; line-height:1.7; text-align:left; }
  .hint { display:none; margin-top:12px; background:#16161A; border:1px solid #2C2C31; border-radius:10px;
          padding:10px 12px; font-size:13.5px; line-height:1.9; color:#A9A492; text-align:left; }
  .hint b { color:#F5F0E1; }
  .sp { display:inline-block; width:15px; height:15px; border:2px solid #C9A227;
        border-top-color:transparent; border-radius:50%; animation:spin .8s linear infinite; vertical-align:-3px; }
  @keyframes spin { to { transform:rotate(360deg); } }
</style>
</head>
<body>
<div class="card">
  <h1>📍 ระบุตำแหน่งของคุณ</h1>
  <p id="status"><span class="sp"></span> กำลังเตรียมตัว...</p>
  <div id="result" style="display:none">
    <div class="coords" id="coords">-</div>
    <a class="maplink" id="maplink" href="#" target="_blank" rel="noopener">เปิดใน Google Maps ↗</a>
  </div>
  <button id="send" style="display:none">✅ ส่งตำแหน่งเข้าแชท</button>
  <button id="copy" class="secondary" style="display:none">📋 คัดลอกข้อความพิกัด</button>
  <button id="retry" class="secondary" style="display:none">🔄 ลองหาตำแหน่งใหม่</button>
  <div id="err" class="err" style="display:none"></div>
  <div id="hint" class="hint">
    <b>ถ้าปุ่มส่งไม่ขึ้น หรือกดแล้วไม่ทำงาน</b><br>
    • ต้องเปิดหน้านี้จากในแชท LINE (กดปุ่ม 📍 location ที่เมนู)<br>
    • กด "คัดลอก" แล้ว<b>วางในแชท</b>ส่งให้บอทแทนได้<br>
    • iPhone: การตั้งค่า → ความเป็นส่วนตัว → บริการตำแหน่ง → LINE = อนุญาต<br>
    • Android: การตั้งค่า → ตำแหน่ง → เปิด + อนุญาตให้ LINE
  </div>
</div>
<script src="https://static.line-scdn.net/liff/edge/2/sdk.js"></script>
<script>
(function () {
  var LIFF_ID = "__LIFF_ID__";
  var statusEl = document.getElementById("status");
  var coordsEl = document.getElementById("coords");
  var mapEl = document.getElementById("maplink");
  var resultEl = document.getElementById("result");
  var sendBtn = document.getElementById("send");
  var copyBtn = document.getElementById("copy");
  var retryBtn = document.getElementById("retry");
  var errEl = document.getElementById("err");
  var hintEl = document.getElementById("hint");
  var pos = null, canSend = false, sending = false;

  function show(el, on) { el.style.display = on ? "" : "none"; }
  function setStatus(html) { statusEl.innerHTML = html; }
  function showErr(msg, retry) {
    errEl.innerHTML = msg;
    show(errEl, true);
    show(retryBtn, !!retry);
    setStatus("");
  }
  function payload() {
    return "LOCATION " + pos.lat.toFixed(6) + "," + pos.lng.toFixed(6);
  }
  function onGot(p) {
    pos = { lat: p.coords.latitude, lng: p.coords.longitude };
    coordsEl.textContent = pos.lat.toFixed(6) + ", " + pos.lng.toFixed(6);
    mapEl.href = "https://www.google.com/maps?q=" + pos.lat.toFixed(6) + "," + pos.lng.toFixed(6);
    show(resultEl, true);
    show(copyBtn, true);
    show(retryBtn, false);
    show(errEl, false);
    if (canSend) {
      show(sendBtn, true);
      setStatus("✅ ได้ตำแหน่งแล้ว<br>กดปุ่มด้านล่างเพื่อส่งเข้าแชท");
    } else {
      show(sendBtn, false);
      show(hintEl, true);
      setStatus("✅ ได้ตำแหน่งแล้ว แต่ส่งอัตโนมัติไม่ได้<br>คัดลอกแล้ววางในแชทแทน");
    }
  }
  function onGeoErr(e) {
    var msg = "หาตำแหน่งไม่สำเร็จ";
    if (e && e.code === 1) { msg = "คุณยังไม่อนุญาตให้เข้าถึงตำแหน่ง"; }
    else if (e && e.code === 2) { msg = "สัญญาณตำแหน่งใช้ไม่ได้ (ลองกลางแจ้ง หรือเปิด GPS + Wi-Fi)"; }
    else if (e && e.code === 3) { msg = "หมดเวลาคอยตำแหน่ง"; }
    show(hintEl, true);
    showErr("❌ " + msg + "<br>แตะ 'ลองใหม่' หรือคัดลอกพิกัดเอง", true);
  }
  function getLoc() {
    show(errEl, false);
    show(retryBtn, false);
    if (!navigator.geolocation) {
      show(hintEl, true);
      showErr("❌ อุปกรณ์นี้ไม่รองรับการระบุตำแหน่ง", false);
      return;
    }
    setStatus('<span class="sp"></span> กำลังขอตำแหน่งจากเครื่อง...');
    navigator.geolocation.getCurrentPosition(onGot, onGeoErr,
      { enableHighAccuracy: true, timeout: 12000, maximumAge: 0 });
  }
  function send() {
    if (sending || !pos || !window.liff) { return; }
    sending = true;
    sendBtn.disabled = true;
    sendBtn.textContent = "⏳ กำลังส่ง...";
    var msg = payload();
    liff.sendMessages([{ type: "text", text: msg }]).then(function () {
      setStatus("✅ ส่งเรียบร้อย — กำลังปิดหน้าต่าง...");
      show(sendBtn, false);
      setTimeout(function () {
        try { (liff.closeWindow ? liff.closeWindow() : liff.close()); } catch (e) {}
      }, 500);
    }).catch(function (err) {
      sending = false;
      sendBtn.disabled = false;
      sendBtn.textContent = "✅ ส่งตำแหน่งเข้าแชท";
      show(hintEl, true);
      showErr("❌ ส่งข้อความไม่สำเร็จ: " + (err && err.message ? err.message : err) +
              "<br>ต้องเปิดจากในแชท LINE — หรือใช้ปุ่มคัดลอกด้านล่าง", false);
    });
  }
  function legacyCopy(t, done) {
    try {
      var ta = document.createElement("textarea");
      ta.value = t;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      var ok = document.execCommand("copy");
      document.body.removeChild(ta);
      if (ok) { done(); } else { showErr("คัดลอกไม่สำเร็จ — กดค้างที่บรรทัดพิกัดเพื่อคัดลอกเอง", false); }
    } catch (e) { showErr("คัดลอกไม่สำเร็จ — กดค้างที่บรรทัดพิกัดเพื่อคัดลอกเอง", false); }
  }
  function copy() {
    if (!pos) { return; }
    var t = payload();
    var done = function () {
      copyBtn.textContent = "✅ คัดลอกแล้ว — วางในแชทได้เลย";
      setStatus("คัดลอกเรียบร้อย<br>กลับไปที่แชท แล้ว<b>วาง + ส่ง</b>ให้บอท");
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(t).then(done).catch(function () { legacyCopy(t, done); });
    } else { legacyCopy(t, done); }
  }
  function initLiff() {
    if (!LIFF_ID || LIFF_ID.indexOf("__") === 0) {
      show(hintEl, true);
      showErr("⚠️ ยังไม่ได้ตั้งค่า <b>LIFF_ID</b> บน Render<br>ดึงตำแหน่งได้แล้ว — คัดลอกไปวางในแชทแทน", false);
      getLoc();
      return;
    }
    if (!window.liff) {
      show(hintEl, true);
      showErr("❌ โหลด LIFF SDK ไม่สำเร็จ (เน็ต/สคริปต์ถูกบล็อก)", true);
      getLoc();
      return;
    }
    liff.init({ liffId: LIFF_ID }).then(function () {
      var inClient = (typeof liff.isInClient === "function") ? liff.isInClient() : true;
      var avail = (typeof liff.isApiAvailable === "function") ? liff.isApiAvailable("sendMessages") : true;
      canSend = !!(inClient && avail);
      if (!inClient) { show(hintEl, true); }
      getLoc();
    }).catch(function (err) {
      canSend = false;
      show(hintEl, true);
      showErr("❌ เปิด LIFF ไม่สำเร็จ: " + (err && err.message ? err.message : err), true);
      getLoc();
    });
  }
  sendBtn.addEventListener("click", send);
  copyBtn.addEventListener("click", copy);
  retryBtn.addEventListener("click", getLoc);
  initLiff();
})();
</script>
</body>
</html>"""

    @app.route("/liff/location", methods=["GET"])
    def liff_location():
        """หน้าดึงตำแหน่งเครื่อง (LIFF Endpoint) — ค่า LIFF_ID ฉีดจาก env ทุกครั้งที่เรียก"""
        liff_id = (os.environ.get("LIFF_ID", "") or "").strip()
        html = LIFF_HTML.replace("__LIFF_ID__", liff_id)
        return html, 200, {"Content-Type": "text/html; charset=utf-8"}


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

        # === Rich Menu คำสั่งลัด 6 ปุ่ม (ต้องอยู่ก่อน logic อื่น) ===
        if text in ["✨ ต้องการโพสต์", "ต้องการโพสต์", "เริ่มต้นระบบ"]:
            p = pending_posts.get(uid)
            if p and (p.get("text") or _imgs(p) or _vids(p)):
                preview = (p.get("text") or "(มีแต่รูป/วิดีโอ)")[:300]
                img_note = _media_note(p)
                line_api.reply_message(event.reply_token, TextMessage(text=f"📋 Draft ปัจจุบัน:\n---\n{preview}\n---\n{img_note}{_loc_note(uid)}\n\nกด 'โพสต์' เพื่อโพสต์ หรือ 'ยกเลิกโพสต์' เพื่อล้าง"))
            else:
                line_api.reply_message(event.reply_token, TextMessage(text="🚀 เริ่มต้นระบบ — ส่งรูป/วิดีโอ + ข้อความมาได้เลย แล้วกด 'โพสต์'"))
            return

        if text in ["แก้ไขรูป", "แก้รูป"]:
            old_files = pending_images.pop(uid, []) + pending_videos.pop(uid, [])
            if uid in pending_posts:
                p0 = pending_posts[uid]
                old_files += _imgs(p0) + _vids(p0)
                p0["images"] = []
                p0["videos"] = []
                p0["image_url"] = None
            for fp in old_files:
                try:
                    if fp and not fp.startswith("http") and Path(fp).exists():
                        Path(fp).unlink()
                except Exception:
                    pass
            line_api.reply_message(event.reply_token, TextMessage(text="🖼️ ล้างรูปและวิดีโอเก่าออกหมดแล้ว ✅\nส่งรูป/วิดีโอใหม่มาได้เลย"))
            return

        if text in ["แก้ไขข้อความ", "แก้ข้อความ"]:
            if uid in pending_posts:
                pending_posts[uid]["text"] = ""
            line_api.reply_message(event.reply_token, TextMessage(text="✏️ ล้างข้อความเก่าออกหมดแล้ว ✅\nส่งข้อความใหม่มาได้เลย"))
            return

        if text in ["เลือกเพจ", "เปลี่ยนเพจ", "เลือกเพจใหม่"]:
            if FORCE_PAGE_ID:
                pg_name = PAGES.get(FORCE_PAGE_ID, {}).get("name", FORCE_PAGE_ID)
                p = pending_posts.get(uid)
                if p is not None:
                    p["page_id"] = FORCE_PAGE_ID
                    p["page_id_selected"] = True
                    p.pop("awaiting_page", None)
                    link_richmenu_to_user(uid, RICHMENU_MAIN_ID)
                    preview = (p.get("text") or "(ไม่มีข้อความ)")[:350]
                    sched = f"⏰ ตั้งเวลา {p['schedule'].strftime('%d/%m %H:%M')}" if p.get("schedule") else "⚡ โพสต์ทันที"
                    line_api.reply_message(event.reply_token, TextMessage(text=f"✅ เลือกเพจอัตโนมัติ: {pg_name} (ล็อคไว้)\n📋 Preview:\n---\n{preview}\n---\n{_media_note(p)} | {sched}\n\nกดปุ่ม 'โพสต์' จากเมนูเพื่อยืนยันโพสต์ (หรือพิมพ์ 'ใช่')"))
                else:
                    line_api.reply_message(event.reply_token, TextMessage(text=f"📄 เพจ: {pg_name} (ล็อคไว้ — ส่งรูป/วิดีโอ + ข้อความมาได้เลย)"))
                return
            p = pending_posts.get(uid)
            if p is not None:
                p["awaiting_page"] = True
                p["page_id_selected"] = False
            line_api.reply_message(event.reply_token, _page_choice_message())
            return

        if text in ["โพสต์ใหม่", "เริ่มใหม่", "ล้างทั้งหมด", "ยกเลิกโพสต์", "ยกเลิก"]:
            old_paths = pending_images.pop(uid, []) + pending_videos.pop(uid, [])
            if uid in pending_posts:
                old_paths += _imgs(pending_posts[uid]) + _vids(pending_posts[uid])
            for fp in old_paths:
                try:
                    if fp and not fp.startswith("http") and Path(fp).exists():
                        Path(fp).unlink()
                except Exception:
                    pass
            pending_posts[uid] = {"text": "", "images": [], "videos": [], "image_url": None, "schedule": None, "page_id": None, "page_id_selected": False}
            line_api.reply_message(event.reply_token, TextMessage(text="❌ ยกเลิกโพสต์แล้ว — ล้างรูป วิดีโอ และข้อความหมด\nส่งเนื้อหาใหม่ได้เลย"))
            return

        if text in ["โพสต์"]:
            p = pending_posts.get(uid)
            if not p or (not p.get("text") and not _imgs(p) and not _vids(p)):
                line_api.reply_message(event.reply_token, TextMessage(text="📭 ยังไม่มี draft ให้โพสต์\nส่งรูป/วิดีโอ + ข้อความมาก่อน แล้วกด 'โพสต์' อีกครั้ง"))
                return
            if FORCE_PAGE_ID:
                p["page_id"] = FORCE_PAGE_ID
                p["page_id_selected"] = True
            if not FORCE_PAGE_ID and not p.get("page_id_selected"):
                p["awaiting_page"] = True
                p["auto_post"] = True  # เลือกเพจเสร็จให้โพสต์ทันที ไม่ต้องพิมพ์ 'ใช่' ซ้ำ
                line_api.reply_message(event.reply_token, _page_choice_message())
                return
            pending = pending_posts.pop(uid)
            _ploc = user_location.get(uid)
            final_text = apply_location(pending.get("text"), _ploc)
            result = post_to_facebook(final_text, pending["image_url"], pending["schedule"], pending.get("page_id"), images=pending.get("images"), videos=pending.get("videos"))
            create_draft(final_text, pending["image_url"], pending["schedule"], pending.get("page_id"), images=pending.get("images"), videos=pending.get("videos"))
            pg_name = PAGES.get(pending.get("page_id"), {}).get("name", pending.get("page_id", ""))
            if "success" in result:
                pid = result["response"].get("id") or result["response"].get("post_id") or ""
                reply = f"✅ โพสต์สำเร็จ!\nhttps://facebook.com/{pid}\nเพจ: {pg_name}" + ("\n📍 แนบโลเคชั่นในแคปชันแล้ว" if _ploc else "")
            else:
                reply = f"❌ โพสต์ไม่สำเร็จ ({pg_name}): {result.get('error','')[:300]}"
            line_api.reply_message(event.reply_token, TextMessage(text=reply))
            return

        # === โลเคชั่น + AI คิดแคปชัน (ต้องอยู่ก่อนบล็อก "เลือกเพจ" ไม่งั้นคำสั่งจะโดนกิน) ===
        _loc = parse_location_text(text)
        if _loc:
            _set_location(event, _loc[0], _loc[1], "liff" if text.strip().upper().startswith("LOCATION") else "text")
            return

        _low = text.strip().lower()
        if _low in ["location", "โลเคชั่น", "โลเคชั่นปัจจุบัน", "ตำแหน่ง", "ตำแหน่งปัจจุบัน", "ดูโลเคชั่น"]:
            _location_help(event)
            return
        if _low in ["ปิด location", "ปิดโลเคชั่น", "ปิด โลเคชั่น", "ลบ location", "ลบโลเคชั่น",
                    "เลิกแนบ location", "เลิกแนบโลเคชั่น", "ไม่เอา location"]:
            if user_location.pop(uid, None):
                line_api.reply_message(event.reply_token, TextMessage(
                    text="📍 ปิดการแนบโลเคชั่นแล้ว\nโพสต์ถัดไปจะไม่มีลิงก์ตำแหน่ง\n(พิมพ์ 'location' เพื่อดู/ตั้งใหม่)"))
            else:
                line_api.reply_message(event.reply_token, TextMessage(
                    text="ℹ️ ยังไม่มีโลเคชั่นที่ตั้งไว้อยู่แล้ว\n(พิมพ์ 'location' เพื่อดูวิธีตั้ง)"))
            return

        if _low in ["คิดแคปชั่น", "เขียนแคปชั่น", "คิดแคปชั่นจากภาพ", "เขียนแคปชั่นจากภาพ",
                    "คิดแคปชัน", "เขียนแคปชัน", "คิด caption", "เขียน caption",
                    "ให้ ai เขียนแคปชั่น", "ให้ ai คิดแคปชั่น", "คิดแคปชั่นให้หน่อย"]:
            _do_ai_caption(uid, event)
            return

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
                line_api.reply_message(event.reply_token, _page_choice_message("❓ เลือกเพจไม่ถูก\nแตะปุ่มข้างล่าง หรือพิมพ์ 1 / 2"))
                return
            link_richmenu_to_user(uid, RICHMENU_MAIN_ID)  # เด้งเมนูกลับหน้าหลัก
            # ถ้ามาจากปุ่ม "โพสต์" ให้โพสต์ทันทีหลังเลือกเพจ ไม่ต้องพิมพ์ 'ใช่' ซ้ำ
            if pending_posts[uid].pop("auto_post", None):
                pending = pending_posts.pop(uid)
                _ploc = user_location.get(uid)
                final_text = apply_location(pending.get("text"), _ploc)
                result = post_to_facebook(final_text, pending["image_url"], pending["schedule"], pending.get("page_id"), images=pending.get("images"), videos=pending.get("videos"))
                create_draft(final_text, pending["image_url"], pending["schedule"], pending.get("page_id"), images=pending.get("images"), videos=pending.get("videos"))
                pg_name = PAGES.get(pending.get("page_id"), {}).get("name", pending.get("page_id", ""))
                if "success" in result:
                    pid = result["response"].get("id") or result["response"].get("post_id") or ""
                    reply = f"✅ โพสต์สำเร็จ!\nhttps://facebook.com/{pid}\nเพจ: {pg_name}" + ("\n📍 แนบโลเคชั่นในแคปชันแล้ว" if _ploc else "")
                else:
                    reply = f"❌ โพสต์ไม่สำเร็จ ({pg_name}): {result.get('error','')[:300]}"
                line_api.reply_message(event.reply_token, TextMessage(text=reply))
                return
            # หลังเลือกเพจแล้ว ถามยืนยัน
            p = pending_posts[uid]
            pg_name = PAGES.get(p["page_id"], {}).get("name", p["page_id"])
            preview = p["text"][:350] if p["text"] else "(ไม่มีข้อความ)"
            img_note = _media_note(p)
            sched_note = f"⏰ ตั้งเวลา {p['schedule'].strftime('%d/%m %H:%M')}" if p["schedule"] else "⚡ โพสต์ทันที"
            reply = f"✅ เลือกเพจ: {pg_name}\n📋 Preview:\n---\n{preview}\n---\n{img_note} | {sched_note}\n\nกดปุ่ม 'โพสต์' จากเมนูเพื่อยืนยันโพสต์ (หรือพิมพ์ 'ใช่')"
            line_api.reply_message(event.reply_token, TextMessage(text=reply))
            return

        # 1. ถ้าพิมพ์ "ใช่" / "ยืนยัน" / "โพสต์เลย" -> ต้องเลือกเพจก่อนโพสต์เสมอ (ถ้า FORCE_PAGE_ID จะโพสต์เลยไม่ถาม)
        if text in ["ใช่", "ใช่ครับ", "ยืนยัน", "โพสต์เลย", "ตกลง"] and uid in pending_posts:
            if FORCE_PAGE_ID:
                pending_posts[uid]["page_id"] = FORCE_PAGE_ID
                pending_posts[uid]["page_id_selected"] = True
            # บังคับถามเลือกเพจทุกครั้ง (ตามคำขอ) - ข้ามถ้า FORCE
            if not FORCE_PAGE_ID and not pending_posts[uid].get("awaiting_page") and not pending_posts[uid].get("page_id_selected"):
                line_api.reply_message(event.reply_token, _page_choice_message())
                pending_posts[uid]["awaiting_page"] = True
                return
            if not FORCE_PAGE_ID and pending_posts[uid].get("awaiting_page"):
                line_api.reply_message(event.reply_token, _page_choice_message())
                return
            pending = pending_posts.pop(uid)
            _ploc = user_location.get(uid)
            final_text = apply_location(pending.get("text"), _ploc)
            result = post_to_facebook(final_text, pending["image_url"], pending["schedule"], pending.get("page_id"), images=pending.get("images"), videos=pending.get("videos"))
            create_draft(final_text, pending["image_url"], pending["schedule"], pending.get("page_id"), images=pending.get("images"), videos=pending.get("videos"))
            pg_name = PAGES.get(pending.get("page_id"), {}).get("name", pending.get("page_id", "ก๊อดเองแม่ตั้งให้"))
            if "success" in result:
                pid = result["response"].get("id") or result["response"].get("post_id") or ""
                reply = f"✅ โพสต์สำเร็จ!\nhttps://facebook.com/{pid}\nเพจ: {pg_name}" + ("\n📍 แนบโลเคชั่นในแคปชันแล้ว" if _ploc else "")
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

        # 2.1 "สร้างรูป" -> สร้างรูป AI เสมอ / "2" เฉพาะตอน draft ยังว่าง
        # (draft มีของแล้วเลข 2 = เลือกเพจ ดูบล็อกเลข 1/2 ด้านล่าง)
        _ai_empty = uid in pending_posts and not (pending_posts[uid].get("text") or _imgs(pending_posts[uid]) or _vids(pending_posts[uid]))
        if (text.strip() in ["สร้างรูป", "ให้ AI สร้างรูป", "สร้างรูปด้วย"] or (text.strip() in ["2", "2."] and _ai_empty)) and uid in pending_posts:
            pending = pending_posts[uid]
            prompt = pending["text"][:100] if pending["text"] else "football stadium"
            img_url = gemini_image(prompt)
            pending.setdefault("images", []).append(img_url)
            for fp in pending_images.pop(uid, []):
                if fp not in pending["images"]:
                    pending["images"].append(fp)
            _sync_first(pending)
            reply = f"🎨 สร้างรูป AI แล้ว:\n{img_url}\n\n📋 Preview:\n{pending['text'][:300]}\n\nพิมพ์ 'ใช่' เพื่อยืนยันโพสต์พร้อมรูปนี้"
            line_api.reply_message(event.reply_token, TextMessage(text=reply))
            return

        # ชื่อเพจ: พิมพ์/แตะตอนไหนก็เลือกเพจได้เลย ไม่กินแคปชัน
        # (exact match เท่านั้น แคปชันที่มีชื่อเพจปนอยู่ยังเป็นแคปชันปกติ)
        _pick = text.strip().lower()
        _pid = ("104158371681569" if _pick in ["ก๊อดเองแม่ตั้งให้", "ก๊อดเอง"]
                else "788732444316483" if _pick in ["getup deal", "getupdeal", "getup"]
                else None)
        if _pid:
            if uid not in pending_posts:
                line_api.reply_message(event.reply_token, TextMessage(text="📌 รับทราบเพจแล้ว แต่ยังไม่มี draft\nส่งรูป/วิดีโอ + ข้อความมาก่อน แล้วค่อยกด 'โพสต์'"))
                return
            _apply_page(uid, _pid, event)
            return

        # เลข 1/2: ถ้า draft มีของแล้ว = เลือกเพจ / ถ้ายังว่าง = ปล่อยผ่าน (2 = สร้างรูป AI, 1 = ถามรูป)
        if text.strip() in ["1", "1.", "2", "2."]:
            p = pending_posts.get(uid)
            if p is not None and not p.get("awaiting_page") and (p.get("text") or _imgs(p) or _vids(p)):
                _apply_page(uid, "104158371681569" if text.strip().startswith("1") else "788732444316483", event)
                return

        # 3. ข้อความใหม่ - แยกเวลาและทำความสะอาด
        schedule = parse_schedule(text)
        clean = re.sub(r'โพสต์เลย|โพสท์เลย|โพสต์\s*\d.*|โพสท์\s*\d.*|ตั้งเวลา.*|\b\d{1,2}:\d{2}\b|พรุ่งนี้', '', text).strip()
        if not clean:
            clean = text

        new_images = pending_images.pop(uid, [])
        new_videos = pending_videos.pop(uid, [])

        # ถ้าไม่มีรูป และไม่มีข้อความชัดเจน ถามเรื่องรูป
        if not new_images and not new_videos and not any(k in text for k in ["โพสต์เลย", "ตั้งเวลา"]) and len(clean) < 5:
            line_api.reply_message(event.reply_token, TextMessage(text="📸 ไม่เห็นรูปแนบ ต้องการใช้รูปอะไร?\n1. ส่งรูปมา\n2. ให้ AI สร้างรูปสนามใหม่\n3. โพสต์แบบข้อความล้วน\n\nพิมพ์เลขหรือส่งรูปมาได้เลย"))
            pending_posts[uid] = {"text": clean, "images": [], "videos": [], "image_url": None, "schedule": schedule}
            return

        # ถ้า FORCE_PAGE_ID จะล็อคเพจเลยไม่ถาม
        if FORCE_PAGE_ID:
            pending_posts[uid] = {"text": clean, "images": [], "videos": [], "image_url": None, "schedule": schedule, "page_id": FORCE_PAGE_ID, "page_id_selected": True}
        else:
            # ไม่ auto เลือกเพจแล้ว - บังคับถามทุกครั้งก่อนโพสต์
            hint_page = None
            if any(k in text.lower() for k in ["getup", "get up"]):
                hint_page = "788732444316483"
            elif "ก๊อด" in text:
                hint_page = "104158371681569"
            pending_posts[uid] = {"text": clean, "images": [], "videos": [], "image_url": None, "schedule": schedule, "page_id": None, "page_id_selected": False}
            if hint_page:
                pending_posts[uid]["hint_page"] = hint_page
        # รวมรูป/วิดีโอที่ส่งมาก่อนหน้าเข้ากับ draft
        for fp in new_images:
            if fp not in pending_posts[uid]["images"]:
                pending_posts[uid]["images"].append(fp)
        for fp in new_videos:
            if fp not in pending_posts[uid]["videos"]:
                pending_posts[uid]["videos"].append(fp)
        _sync_first(pending_posts[uid])
        preview = clean[:350] if clean else "(ไม่มีข้อความ - มีแต่รูป/วิดีโอ)"
        img_note = _media_note(pending_posts[uid])
        if schedule:
            sched_note = f"⏰ ตั้งเวลา {schedule.strftime('%d/%m %H:%M น.')} (ต้องล่วงหน้า 10 นาที)"
        else:
            sched_note = "⚡ จะโพสต์ทันที"
        if FORCE_PAGE_ID:
            pg_name = PAGES[FORCE_PAGE_ID]["name"]
            page_note = f"\U0001f4c4 \u0e40\u0e1e\u0e08: {pg_name} (\u0e25\u0e47\u0e2d\u0e04\u0e44\u0e27\u0e49 - \u0e01\u0e14 'โพสต์' \u0e40\u0e1e\u0e37\u0e48\u0e2d\u0e42\u0e1e\u0e2a\u0e15\u0e4c\u0e40\u0e25\u0e22)"
        elif hint_page:
            pg_name = PAGES[hint_page]["name"]
            page_note = f"📄 เพจที่เดาจากข้อความ: {pg_name} (แตะปุ่มหรือพิมพ์ 1/2 เพื่อยืนยัน)"
        else:
            page_note = "📄 เพจ: ยังไม่ได้เลือก (จะให้เลือกตอนกด 'โพสต์')"

        reply = f"📋 Preview ก่อนโพสต์:\n---\n{preview}\n---\n{img_note} | {sched_note}\n{page_note}{_loc_note(uid)}\n\n✅ กดปุ่ม 'โพสต์' จากเมนูเพื่อโพสต์เลย (หรือพิมพ์ 'ใช่')\n✏️ พิมพ์ข้อความใหม่เพื่อแก้ไข"
        line_api.reply_message(event.reply_token, TextMessage(text=reply))

    @handler.add(MessageEvent, message=LocationMessage)
    def handle_location(event):
        """ผู้ใช้แชร์ตำแหน่งจาก LINE (ปุ่ม 📍 ข้างช่องพิมพ์) -> เก็บเป็นโลเคชั่นของ draft"""
        try:
            m = event.message
            _set_location(event, m.latitude, m.longitude, "line")
        except Exception as e:
            print(f"handle_location error: {e}")
            line_api.reply_message(event.reply_token, TextMessage(text=f"❌ อ่านตำแหน่งไม่สำเร็จ: {str(e)[:150]}"))

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
            # เก็บไฟล์ local ไว้โพสต์ตรง ไม่ต้องอัป catbox (สะสมได้หลายรูป)
            local_path = str(img_path)
            pending_images.setdefault(uid, []).append(local_path)
            p = pending_posts.get(uid)
            if p is None:
                p = pending_posts[uid] = {"text": "", "images": [], "videos": [], "image_url": None, "schedule": None}
            p.setdefault("images", [])
            if local_path not in p["images"]:
                p["images"].append(local_path)
            _sync_first(p)
            n = len(p["images"])
            _tip = "" if (p.get("text") or "").strip() else "\n💡 พิมพ์ 'คิดแคปชั่น' ให้ AI เขียนจากภาพนี้"
            line_api.reply_message(event.reply_token, TextMessage(text=f"📸 รับรูปที่ {n} แล้ว! ✅{_tip}\nส่งรูป/วิดีโอเพิ่มหรือส่งแคปชันได้เลย แล้วกด 'โพสต์' จากเมนู"))
        except Exception as e:
            print(f"handle_image error: {e}")
            line_api.reply_message(event.reply_token, TextMessage(text=f"❌ รับรูปไม่สำเร็จ: {str(e)[:200]}"))

    @handler.add(MessageEvent, message=VideoMessage)
    def handle_video(event):
        uid = event.source.user_id
        msg_id = event.message.id
        try:
            content = line_api.get_message_content(msg_id)
            vid_path = MEDIA_DIR / f"{msg_id}.mp4"
            with open(vid_path, "wb") as f:
                for chunk in content.iter_content():
                    f.write(chunk)
            local_path = str(vid_path)
            pending_videos.setdefault(uid, []).append(local_path)
            p = pending_posts.get(uid)
            if p is None:
                p = pending_posts[uid] = {"text": "", "images": [], "videos": [], "image_url": None, "schedule": None}
            p.setdefault("videos", [])
            if local_path not in p["videos"]:
                p["videos"].append(local_path)
            m = len(p["videos"])
            line_api.reply_message(event.reply_token, TextMessage(text=f"🎬 รับวิดีโอที่ {m} แล้ว! ✅\nส่งรูป/วิดีโอเพิ่มหรือส่งแคปชันได้เลย แล้วกด 'โพสต์' จากเมนู\n(โพสต์ได้ครั้งละ 1 วิดีโอ ไฟล์ไม่ควรเกิน ~200MB)"))
        except Exception as e:
            print(f"handle_video error: {e}")
            line_api.reply_message(event.reply_token, TextMessage(text=f"❌ รับวิดีโอไม่สำเร็จ: {str(e)[:200]}"))

    if __name__ == "__main__":
        app.run(host="0.0.0.0", port=8080, debug=False, use_reloader=False)
else:
    print("LINE SDK not installed - run: pip install flask line-bot-sdk")
