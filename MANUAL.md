# คู่มือระบบโพสต์อัตโนมัติ OpenClaw + LINE → Facebook

**เพจ:** ก๊อดเองแม่ตั้งให้ (104158371681569) - ล็อกเพจเดียว
**LINE OA:** @308fvqux (ก๊อดเองแม่ตั้งให้)
**Facebook App:** Post_Automation (1754294572508532)
**GitHub Cloud:** https://github.com/kanchat-y/line-fb-webhook
**Cloud URL (Render):** https://line-fb-webhook.onrender.com

> **Server Local = OpenClaw Local** (รันบนเครื่องคุณ: Gateway + Flask + Tunnel)
> **Server Cloud = GitHub Cloud** (รันบนคลาวด์: GitHub → Render)

---

## สารบัญ
- [ภาพรวมระบบ](#ภาพรวมระบบ)
- [1. ระบบ Local Server = OpenClaw Local](#1-ระบบ-local-server--openclaw-local-ต้องเปิดคอม)
- [2. ระบบ Cloud Server = GitHub Cloud](#2-ระบบ-cloud-server--github-cloud-render-ปิดคอมได้)
- [การใช้งาน LINE](#การใช้งาน-line-8-ข้อที่ล็อกไว้)
- [การต่ออายุ Token 60 วัน](#การต่ออายุ-token-60-วัน)
- [ปัญหาและการแก้ไข](#ปัญหาและการแก้ไข)

---

## ภาพรวมระบบ

```
LINE OA (@308fvqux)
   ↓ (ส่งไอเดีย+รูป)
Webhook (/line-webhook)
   ↓
Flask app.py (autopost/line-webhook/app.py)
   ├─ เก็บรูป → autopost/media/*.jpg
   ├─ ถามยืนยัน (ตามสเปค 8 ข้อ)
   └─ เรียก Graph API v23.0
          ↓
   Facebook Page 104158371681569 (ก๊อดเองแม่ตั้งให้)
   ↓
autopost/calendar.json + published/
```

**สเปคที่ล็อกไว้ 8 ข้อ:**
1. ส่งแล้วถาม `โพสต์เลยหรือตั้งเวลา?` ก่อนโพสต์เสมอ
2. ใช้ไอเดีย+รูปที่ส่งเป็นหลัก แล้วถาม `อยากให้ช่วยเกลาไหม?`
3. ไม่แนบรูป → ถาม `ต้องการรูปแบบไหน? (ส่งรูปมา / AI สร้าง / ข้อความล้วน)`
4. ตั้งเวลาต้องระบุเอง (`19:45`, `พรุ่งนี้ 09:00`) และต้องยืนยันก่อนโพสต์
5. LINE คนเดียว (U515f76be109976684634691f46bda0af)
6. มีถาม-ตอบ preview ก่อนโพสต์จริง พิมพ์ `ใช่` ถึงโพสต์
7. LINE OA ชื่อ `ก๊อดเองแม่ตั้งให้` ความบันเทิง
8. ใช้ OpenClaw LINE Channel + Flask Webhook

---

## 1. ระบบ Local Server = OpenClaw Local (ต้องเปิดคอม)

### 1.1 สิ่งที่ต้องติดตั้ง
- Node.js 24.16.0+ (ผ่าน nvm)
- Python 3.12 + pip
- OpenClaw 2026.9.4 (`npm install -g openclaw`)
- Git

### 1.2 ติดตั้ง OpenClaw + Gateway (ครั้งเดียว)
```powershell
nvm install 24.16.0
nvm use 24.16.0
npm install -g openclaw@latest
openclaw gateway install --port 18789 --token openclaw123
# ตั้งค่า auth
openclaw config set gateway.auth.token openclaw123
openclaw gateway restart
# เชื่อม Companion: เปิด OpenClaw Windows Companion → Direct → ws://127.0.0.1:18789 + openclaw123 → Approve
```

### 1.3 ตั้งค่า Facebook App
- https://developers.facebook.com/apps/1754294572508532/settings/basic/
  - Privacy Policy: `https://www.facebook.com/privacy/explanation`
  - Terms: `https://www.facebook.com/terms/`
  - Category: ธุรกิจ
- เพิ่มกรณีการใช้งาน: `จัดการทุกอย่างบนเพจของคุณ` → เพิ่ม `pages_manage_posts`, `pages_read_engagement`, `pages_show_list`
- สร้าง Token: https://developers.facebook.com/tools/explorer/?app_id=1754294572508532 → ติ๊ก 3 ตัว → Generate → ได้ `EAAG...` (1 ชม.)
- แลกเป็น 60 วัน:
  ```powershell
  # ต้องมี App Secret (กด แสดง ตรง ข้อมูลลับของแอพ)
  https://graph.facebook.com/oauth/access_token?grant_type=fb_exchange_token&client_id=1754294572508532&client_secret=APP_SECRET&fb_exchange_token=SHORT_TOKEN
  ```
  จะได้ `EAAY...` 60 วัน (`expires_in: 5183999`)
- ใส่ในเครื่อง: `setx META_ACCESS_TOKEN "EAAY..."`

### 1.4 ตั้งค่า LINE OA
- https://manager.line.biz → เลือก `ก๊อดเองแม่ตั้งให้ @308fvqux` → Settings → Messaging API → Enable
- https://developers.line.biz → Provider `Post_Automation` → Channel `ก๊อดเองแม่ตั้งให้` → Copy:
  - `Channel Secret: 843336fe6197dbb102465d974b862570`
  - `Channel Access Token: ZZtMaUZ...`

### 1.5 รัน Webhook Local
```powershell
pip install flask line-bot-sdk requests gunicorn
$env:LINE_CHANNEL_SECRET="843336fe..."
$env:LINE_CHANNEL_ACCESS_TOKEN="ZZtMaUZ..."
$env:META_ACCESS_TOKEN="EAAY..."
python autopost/line-webhook/app.py  # รันที่ :8080
```
- เปิด tunnel:
```powershell
# วิธี 1: cloudflared (แนะนำ)
cloudflared tunnel --url http://127.0.0.1:8080
# จะได้ https://xxx.trycloudflare.com

# วิธี 2: localtunnel
npx localtunnel --port 8080
```
- เอา `https://xxx.trycloudflare.com/line-webhook` ไปใส่ LINE Developers → Webhook URL → Verify → เปิด Use webhook = On

### 1.6 ทดสอบ
- ส่งรูป + ข้อความใน LINE OA → บอทจะถามตาม flow → พิมพ์ `ใช่` → โพสต์ลงเพจทันที
- เช็ค `autopost/calendar.json` และ https://facebook.com/991675850550798

### 1.7 ข้อจำกัด Local
- ต้องเปิดคอม + Flask + cloudflared ตลอด / ปิดแล้ว LINE จะ 503
- URL tunnel เปลี่ยนทุกครั้งที่รันใหม่ ต้องไปแก้ Webhook URL ใหม่

---

## 2. ระบบ Cloud Server = GitHub Cloud (Render) (ปิดคอมได้)

### 2.1 เตรียมไฟล์ (ทำแล้ว)
- `autopost/line-webhook/app.py` - Webhook หลัก (มี /ping กันหลับ)
- `requirements.txt` - Flask==3.1.0, line-bot-sdk==3.12.0, requests, gunicorn
- `Procfile` - `web: gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --timeout 30`
- `runtime.txt` - `python-3.12.7`
- Push ขึ้น GitHub: https://github.com/kanchat-y/line-fb-webhook.git

### 2.2 Deploy Render (ครั้งเดียว)
1. https://dashboard.render.com → New Web Service → Connect `kanchat-y/line-fb-webhook`
2. Build: `pip install -r requirements.txt` / Start: `gunicorn app:app`
3. Environment → Add:
   - `LINE_CHANNEL_SECRET=843336fe6197dbb102465d974b862570`
   - `LINE_CHANNEL_ACCESS_TOKEN=ZZtMaUZiLY1Ud6a+6ofbA/4wVTIslIzDNfGNa+5FyqWtHRmomUk/StGpbOIGdsD/4GzIDwYN9LiBeimd6h24tIeR/8I4QR/oQJzbWjxKaE6Y2agKKhw3rmaO2RbqqwZos53incopjnwIJY+3BFPSzwdB04t89/1O/w1cDnyilFU=`
   - `META_ACCESS_TOKEN=EAAY7hYjTZAXQBSbSiSf92yI205U1wpif8sOE20ag7Um1fW36nxNupv9KXFETWEHwsVluCk52CNZAnJTB865MJgiOYcKhn2mjreQSWdZBqJwDCmDgnVKQQFlXU30BpdSyN7Wx8GFY1BC3dZByFjLbYQ3MwxfGGeWPlOnqLRN6RcR5PewSsMYtHeyL9Y9m` (อัน 60 วัน)
4. Create → รอ 1 นาที → ได้ URL `https://line-fb-webhook.onrender.com`

### 2.3 ตั้ง LINE Webhook ชี้ไป Cloud
- LINE Developers → Webhook URL → `https://line-fb-webhook.onrender.com/line-webhook` → Update → Verify → Success

### 2.4 กันหลับ (ฟรี)
- Render Free จะ sleep ถ้าไม่มีคนเข้า 15 นาที → LINE จะตอบช้า 30 วิ
- ไป https://cron-job.org → Create Job → URL `https://line-fb-webhook.onrender.com/ping` → ทุก 10 นาที → Save
- หรือ https://uptimerobot.com ตั้งแบบเดียวกัน

### 2.5 ทดสอบ Cloud
- ปิดคอมได้เลย → ส่ง LINE `ทดสอบ` → บอทตอบและโพสต์ได้ปกติ

### 2.6 ข้อดี Cloud
- ไม่ต้องเปิดคอม 24 ชม.
- URL ถาวร ไม่เปลี่ยนเหมือน tunnel
- ฟรี 750 ชม./เดือน พอ 1 service ทั้งเดือน

---

## การใช้งาน LINE (8 ข้อที่ล็อกไว้)

**ส่งใน LINE OA @308fvqux:**

| คุณส่ง | บอทตอบ | คุณตอบกลับ |
|--------|--------|------------|
| รูป+ข้อความ `สนามใหม่แมนยู... โพสต์เลย ช่วยเกลาด้วย` | Preview: `📋 Preview... มีรูป | จะโพสต์ทันที` + `พิมพ์ ใช่ เพื่อยืนยัน` | `ใช่` → โพสต์ทันที |
| ข้อความอย่างเดียว ไม่มีรูป | `📸 ไม่เห็นรูป ต้องการรูปอะไร? 1.ส่งรูปมา 2.AI สร้าง 3.ข้อความล้วน` | ส่งรูปหรือพิมพ์ `3` |
| `ตั้งเวลา 19:45` | `⏰ ตั้งเวลา 15/09 19:45` + Preview | `ใช่` → ตั้งเวลา (ต้องล่วงหน้า 10 นาที) |
| `พรุ่งนี้ 09:00` | `⏰ ตั้งเวลา 16/09 09:00` | `ใช่` |
| `ช่วยเกลา` | `✨ เกลาแคปชันให้แล้ว: ...` + hashtags | `ใช่` |

**ตัวอย่างที่ทดสอบสำเร็จ:**
- 15/09 15:18 โพสต์สนามใหม่ 100k ที่นั่ง + รูป AI → `104158371681569_991786143873102` https://www.facebook.com/991675850550798/posts/991786143873102
- 15/09 17:33 โพสต์ Nike elite bag → `104158371681569_992225487162501`

---

## การต่ออายุ Token 60 วัน

Token หมดทุก 60 วัน (`expires_at` ดูได้จาก `debug_token`) ต่อแบบนี้:

1. Graph API Explorer → Generate `EAAG...` ใหม่ (1 ชม.)
2. แลกเป็น 60 วัน:
```
https://graph.facebook.com/oauth/access_token?grant_type=fb_exchange_token&client_id=1754294572508532&client_secret=a62b12021e733bfd1d38e2050a8bceee&fb_exchange_token=EAAG...
```
3. ได้ `EAAY...` ใหม่ → `setx META_ACCESS_TOKEN "EAAY..."` (เครื่อง) + Render → Environment → แก้ `META_ACCESS_TOKEN` → Save

Page Token ที่ได้จาก `long-lived user token` จะเป็น `expires: 0` (ไม่หมดอายุ) โพสต์ได้ตลอดถ้า User Token ยังไม่หมด

---

## ปัญหาและการแก้ไข

| อาการ | สาเหตุ | แก้ |
|-------|--------|-----|
| LINE ตอบ `OpenClaw: access not configured` | ยังไม่ pairing | รัน `openclaw pairing approve line K4B8LECB` |
| LINE ตอบ `Authentication failed (401)` | LLM provider ไม่ได้ตั้งค่า | เปลี่ยนมาใช้ Flask webhook ตรง (ไม่ต้องใช้ LLM) ตามคู่มือนี้ |
| LINE ขึ้น `503 Service Unavailable` | Flask/Cloudflared ดับ หรือ tunnel เปลี่ยน URL | รัน `python app.py` + `cloudflared tunnel --url http://127.0.0.1:8080` ใหม่ แล้วอัปเดต Webhook URL |
| LINE Verify `405 Method Not Allowed` | ใส่ Webhook URL ผิด path | ต้องเป็น `https://xxx/line-webhook` (มี `-`) ไม่ใช่ `/` หรือ `/line/webhook` |
| LINE Verify `404 Not Found` | ใส่ URL ผิดหรือ Render ยังไม่ Live | เช็ค Render ว่า `Live` และ URL ถูก `https://line-fb-webhook.onrender.com/line-webhook` |
| Facebook `HTTP Error 400: Bad Request` | Token หมดอายุ (1 ชม.) หรือรูป catbox โหลดไม่ได้ | ใช้ Token 60 วัน + อัปโหลดรูปตรงแบบไฟล์ (แก้แล้วใน `app.py`) |
| Facebook `Session has expired` | Token หมดอายุ | เจน Token ใหม่แล้วแลกเป็น 60 วัน |
| คนอื่นดูโพสต์ใน Incognito ขึ้น `ไม่พร้อมใช้งาน` | App ยัง `In Development` | ไป `เผยแพร่` → สลับเป็น `Live` (ต้องกรอก Privacy Policy) |
| WSL ติด `Node 22.22.3 is unsupported` | Companion พยายามใช้ Node 22 | ใช้ Gateway แบบ Windows `openclaw gateway install --port 18789` แทน WSL |

---

## ไฟล์สำคัญ

```
autopost/config.json - ตั้งค่า page_id 104158371681569
autopost/calendar.json - ปฏิทินโพสต์ทั้งหมด
autopost/media/*.jpg - รูปจาก LINE
autopost/line-webhook/app.py - Webhook หลัก
autopost/line-webhook/requirements.txt, Procfile, runtime.txt - สำหรับ Render
C:\Users\OMG\.openclaw\openclaw.json - Config OpenClaw Gateway
C:\Users\OMG\.openclaw\workspace\social-media/ - Sync สำหรับ OpenClaw
```

**สคริปต์ช่วย:**
- `python autopost/scripts/draft.py -m "ข้อความ" --platforms facebook --schedule "2026-09-16T09:00:00+07:00" --approve`
- `python autopost/scripts/autopost.py --dry-run` / `--publish`
- `python autopost/scripts/publish.py post-005 --force`

---

คู่มือนี้สร้างเมื่อ 16 Sep 2026 - ระบบพร้อมใช้งานทั้ง Local และ Cloud
