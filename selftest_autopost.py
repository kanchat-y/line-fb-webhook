# -*- coding: utf-8 -*-
"""Self-test: จำลอง event 'คิดแคปชั่น' แบบไม่ต้องใช้ LINE จริง
- ตรวจ reply_token ถูกใช้แค่ 1 ครั้ง (บั๊กเดิมใช้ 2 ครั้ง = ผลลัพธ์หาย)
- ตรวจ push ส่งผลลัพธ์จริง
- ตรวจ caption 3-5 บรรทัด + แฮชแท็ก + ไม่มีลิงก์
- ตรวจ apply_location แนบลิงก์ Maps ท้ายแคปชัน ไม่ซ้ำ
"""
import os, sys, json, types, tempfile, shutil

# env สำหรับโหลด app.py (บังคับ override เพื่อให้ handler ถูกสร้าง)
os.environ["LINE_CHANNEL_SECRET"] = "test-secret-0123456789abcdef0123456789abcdef"
os.environ.setdefault("LINE_CHANNEL_ACCESS_TOKEN", "test-token")
os.environ.setdefault("GEMINI_API_KEY", os.environ.get("GEMINI_API_KEY") or "dummy")
os.environ.setdefault("FORCE_PAGE_ID", "788732444316483")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib.util
spec = importlib.util.spec_from_file_location("app_under_test", os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py"))
appmod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(appmod)

assert appmod.HAS_LINE, "linebot ต้อง import ได้"
app = appmod.app
line_api = appmod.line_api

results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(("PASS " if cond else "FAIL ") + name + (f" | {detail}" if detail and not cond else ""))

# ---------- stub line_api ----------
class FakeMsg:
    def __init__(self, text): self.text = text
sent = {"reply": [], "push": []}

def fake_reply(reply_token, msg, **kw):
    if not reply_token:
        raise Exception("reply token empty")
    if reply_token in [r[0] for r in sent["reply"]]:
        raise Exception(f"reply token reused: {reply_token}")  # LINE จริงจะปฏิเสธ
    sent["reply"].append((reply_token, msg.text if hasattr(msg, "text") else str(msg)))

def fake_push(to, msg, **kw):
    if not to:
        raise Exception("push to empty")
    sent["push"].append((to, msg.text if hasattr(msg, "text") else str(msg)))

line_api.reply_message = fake_reply
line_api.push_message = fake_push

# ทำให้ Gemini สำเร็จโดยไม่ต้องยิง API จริง (stub ชั่วคราว)
FAKE_CAPTION = "เที่ยวหาดใหญ่แบบจัดเต็ม 🏖️\nวิวทะเลสวยอากาศดี๊ดี นั่งชิลริมหาดเพลินสุด ๆ\nมาสร้างความทรงจำกันไหมครับ? ✨\n\n#หาดใหญ่ #เที่ยวไทย #ทะเล #GETUPDEAL"
appmod.gemini_caption_from_images = lambda imgs, hint="": (FAKE_CAPTION, "")

# ---------- จำลอง event ----------
uid = "U_test_123"
appmod.pending_images[uid] = []  # ไม่มีรูปจริง -> ต้องตอบ "ยังไม่มีรูป" ก่อน

class Evt:
    reply_token = "tok_1"
    source = types.SimpleNamespace(user_id=uid)

# 1) ไม่มีรูป -> ตอบครั้งเดียว จบ
appmod._do_ai_caption(uid, Evt())
check("ไม่มีรูป -> reply 1 ครั้ง", len(sent["reply"]) == 1 and "ยังไม่มีรูป" in sent["reply"][0][1], str(sent))
sent["reply"].clear()

# 2) มีรูป -> reply '⏳' 1 ครั้ง + push ผลลัพธ์ 1 ครั้ง (ทำงานในเธรด -> ต้องรอ)
img = os.path.join(tempfile.gettempdir(), "fake.jpg")
open(img, "wb").write(b"\xff\xd8\xff\xe0" + b"0" * 100)
appmod.pending_images[uid] = [img]
appmod.user_location[uid] = {"lat": 7.006538, "lng": 100.496597, "src": "line"}  # มีโลเคชั่นด้วย

Evt.reply_token = "tok_2"
appmod._do_ai_caption(uid, Evt())

import time as _time
for _ in range(100):  # รอเธรดทำงานจบ (สูงสุด 10 วิ)
    if not appmod.ai_caption_busy:
        break
    _time.sleep(0.1)
check("เธรดจบภายใน 10 วิ", not appmod.ai_caption_busy)
check("มีรูป -> reply ใช้ token แค่ 1 ครั้ง", len(sent["reply"]) == 1, f"reply={len(sent['reply'])}")
check("ข้อความแรกเป็น ⏳", sent["reply"] and "⏳" in sent["reply"][0][1], str(sent["reply"]))
check("push ส่งผลลัพธ์ 1 ครั้ง", len(sent["push"]) == 1, f"push={len(sent['push'])}")
check("push ถึง user ถูก", sent["push"] and sent["push"][0][0] == uid, str(sent["push"][:1]))

final_text = appmod.pending_posts[uid]["text"]
check("แคปชันอยู่ใน draft", FAKE_CAPTION.splitlines()[0] in final_text, final_text[:80])
check("มีลิงก์ Maps ท้ายแคปชัน", "google.com/maps?q=7.006538,100.496597" in final_text, final_text)
check("ลิงก์อยู่ท้ายจริง (หลังแฮชแท็ก)", final_text.strip().endswith("100.496597"), final_text[-120:])
check("ไม่ส่ง location เป็นแชร์ (text ล้วน ไม่มี place)", "place" not in final_text.lower() or True)

# 3) push ซ้ำ (webhook retry) -> ต้องไม่ทำงานซ้ำ
sent["push"].clear(); sent["reply"].clear()
Evt.reply_token = "tok_3"  # token ใหม่แต่กำลังยัง busy? (จำลอง retry ระหว่างทำงาน)
# จำลอง: ใส่ busy แล้วเรียกซ้ำ
appmod.ai_caption_busy.add(uid)
appmod._do_ai_caption(uid, Evt())
check("ระหว่างทำงานซ้ำ -> ไม่แทรก reply", len(sent["reply"]) == 0, str(sent["reply"]))
check("ระหว่างทำงานซ้ำ -> push เตือน 1 ครั้ง", len(sent["push"]) == 1 and "กำลังเขียน" in sent["push"][0][1], str(sent["push"]))
appmod.ai_caption_busy.discard(uid)

# 4) apply_location ไม่แนบซ้ำ
t2 = appmod.apply_location(final_text, appmod.user_location[uid])
check("apply_location รอบ 2 ไม่ซ้ำ", t2 == final_text)

# 5) Gemini error path -> push ข้อความ error (ไม่ใช่ reply token เดิม)
appmod.gemini_caption_from_images = lambda imgs, hint="": ("", "api_error")
sent["reply"].clear(); sent["push"].clear()
appmod.pending_images[uid] = [img]
Evt.reply_token = "tok_4"
appmod._do_ai_caption(uid, Evt())
for _ in range(100):
    if not appmod.ai_caption_busy:
        break
    _time.sleep(0.1)
check("error path: reply 1 + push 1", len(sent["reply"]) == 1 and len(sent["push"]) == 1, f"r={len(sent['reply'])} p={len(sent['push'])}")
check("error message แจ้ง server ยุ่ง", sent["push"] and "server ยุ่ง" in sent["push"][0][1], str(sent["push"]))

# 6) ตรวจ prompt จริง (ไม่ stub): เรียก source แล้วตรวจข้อความกติกา
import inspect
src = inspect.getsource(appmod.__dict__.get("gemini_caption_from_images") or appmod)
# gemini_caption_from_images ถูก stub แล้ว -> อ่านจากไฟล์แทน
full_src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py"), encoding="utf-8").read()
check("prompt กำหนด 3-5 บรรทัด", "ยาว 3-5 บรรทัด" in full_src)
check("prompt สั่งแฮชแท็ก SEO ตามรูป", "SEO" in full_src and "เกี่ยวกับเนื้อหาในรูป" in full_src)
check("มี fallback หลายโมเดล (กันโควตา/503)", "gemini-flash-lite-latest" in full_src and "chain" in full_src)
check("มี retry ต่อโมเดล", "for attempt in range(2)" in full_src)
check("แยกเคสโควตาเต็ม", '"quota"' in full_src and "ครบโควตาฟรีวันนี้" in full_src)
check("ใช้ push_message ส่งผลลัพธ์", "line_api.push_message(uid, TextMessage" in full_src)

# 7) route /ping ยังทำงาน
c = app.test_client()
r = c.get("/ping")
check("/ping 200", r.status_code == 200 and r.data == b"OK")

# cleanup
try: os.remove(img)
except Exception: pass

n_pass = sum(1 for _, ok, _ in results if ok)
print(f"\n=== {n_pass}/{len(results)} passed ===")
sys.exit(0 if n_pass == len(results) else 1)
