# คู่มือมือใหม่ 0 → โพสต์ได้จริงด้วย LINE → Facebook
### สำหรับคนไม่เคยทำมาก่อน ทำตามได้ทีละขั้น

> 📥 **ไฟล์ Setup กดรันได้เลย (ไม่ต้องพิมพ์เอง):**
> - **Local (OpenClaw Local):** [`setup-openclaw-local.ps1`](setup-openclaw-local.ps1) → คลิกขวา `Run with PowerShell` → ทำตามข้อ 2.2-2.3 อัตโนมัติ
> - **Cloud (GitHub Cloud):** [`setup-github-cloud.ps1`](setup-github-cloud.ps1) → คลิกขวา `Run with PowerShell` → ทำตามข้อ 3.1 อัตโนมัติ
> - ไฟล์ทั้ง 2 อยู่ใน `https://github.com/kanchat-y/line-fb-webhook` โหลดแล้วรันได้เลย

### ดาวน์โหลดไฟล์ Setup
```powershell
# วิธีโหลดเร็ว:
git clone https://github.com/kanchat-y/line-fb-webhook.git
# หรือโหลดไฟล์เดี่ยว:
# https://raw.githubusercontent.com/kanchat-y/line-fb-webhook/main/setup-openclaw-local.ps1
# https://raw.githubusercontent.com/kanchat-y/line-fb-webhook/main/setup-github-cloud.ps1
```

**เป้าหมาย:** ส่งไอเดีย+รูปทาง LINE แล้วโพสต์ลง Facebook Page อัตโนมัติ (ทันทีหรือตั้งเวลา) แบบที่เพจ `ก๊อดเองแม่ตั้งให้ (104158371681569)` ทำสำเร็จแล้ว

**มี 2 แบบให้เลือก:**
- **แบบ Local = OpenClaw Local** → รันบนเครื่องคุณ ต้องเปิดคอมตลอด (เหมาะเทส)
- **แบบ Cloud = GitHub Cloud** → รันบนคลาวด์ (GitHub → Render) ปิดคอมก็โพสต์ได้ (แนะนำใช้จริง)

> ทำแบบ Cloud จบในครั้งเดียวใช้ยาว 60 วัน ไม่ต้องเปิดคอม

---

## เตรียมของที่ต้องมี (5 อย่าง)

1. **Facebook Page** ที่คุณเป็น Admin (เช่น `ก๊อดเองแม่ตั้งให้`)
2. **Facebook App** (สร้างที่ https://developers.facebook.com → My Apps → Create App → ประเภท ธุรกิจ)
3. **LINE Official Account** (สร้างที่ https://manager.line.biz → สร้างบัญชี `ก๊อดเองแม่ตั้งให้` @308fvqux)
4. **GitHub Account** (https://github.com/join)
5. **Render Account** (https://dashboard.render.com → Sign up ด้วย GitHub) ฟรี

---

## ส่วนที่ 1: เตรียม Facebook + LINE ให้พร้อม (ทำครั้งเดียว 10 นาที)

### 1.1 Facebook App ตั้งค่าให้โพสต์ได้
1. ไป https://developers.facebook.com/apps/ → เลือก App `Post_Automation` (หรือสร้างใหม่)
2. เมนูซ้าย `การตั้งค่าแอพ > ข้อมูลพื้นฐาน`
   - `นโยบายความเป็นส่วนตัว URL` → `https://www.facebook.com/privacy/explanation`
   - `ข้อกำหนดการให้บริการ URL` → `https://www.facebook.com/terms/`
   - `หมวดหมู่` → `ธุรกิจ` → `บันทึก`
3. เมนูซ้าย `กรณีการใช้งาน` → กด `เพิ่มกรณีการใช้งาน` → เลือก `จัดการทุกอย่างบนเพจของคุณ` → จะได้สิทธิ์ 5 ตัวนี้ขึ้น `พร้อมทดสอบ`:
   - `pages_manage_posts`
   - `pages_read_engagement`
   - `pages_show_list`
   - `business_management`
   - `public_profile`
   - *ถ้ายังไม่ขึ้นให้เข้าไป `ปรับแต่ง` → เพิ่มให้ครบ 5 ตัว*
4. สร้าง Token:
   - ไป https://developers.facebook.com/tools/explorer/?app_id=1754294572508532
   - เลือก App `Post_Automation` → เลือก `User Token` → ติ๊ก 5 ตัวบน → `Generate Access Token` → Copy `EAAG...` (อยู่ได้ 1 ชม.)
5. แลกเป็น 60 วัน (ต้องมี App Secret):
   - ไป `ข้อมูลพื้นฐาน` → ตรง `ข้อมูลลับของแอพ` กด `แสดง` → Copy `App Secret` (เช่น `a62b12021e733bfd1d38e2050a8bceee`)
   - เปิดเบราว์เซอร์วางลิงก์นี้ (แก้ 2 จุด):
     ```
     https://graph.facebook.com/oauth/access_token?grant_type=fb_exchange_token&client_id=1754294572508532&client_secret=APP_SECRET&fb_exchange_token=EAAG...
     ```
     เปลี่ยน `APP_SECRET` เป็นที่ Copy มา, `EAAG...` เป็น Token 1 ชม. → Enter → จะได้ `EAAY...` ยาวๆ `expires_in: 5183999` (≈60 วัน) → Copy ไว้
   - *เช็ค:* เอา `EAAY...` ไปวางที่ https://developers.facebook.com/tools/debug/accesstoken/ → จะเห็น `Expires: 60 days` และ `Scopes` ครบ 5 ตัว

### 1.2 LINE OA เตรียม Webhook
1. https://manager.line.biz → เลือกบัญชี `ก๊อดเองแม่ตั้งให้ @308fvqux` → `Settings` (ฟันเฟือง) → `Messaging API` → `Enable`
2. https://developers.line.biz → Provider `Post_Automation` → Channel `ก๊อดเองแม่ตั้งให้` → จะเห็น:
   - `Channel Secret` → กด `Copy` (32 ตัว `843336fe...`)
   - `Channel Access Token` → กด `Issue` → `Copy` (ยาวๆ `ZZtMaUZ...`)

---

## ส่วนที่ 2: แบบ Local = OpenClaw Local (ต้องเปิดคอม)

**เหมาะ:** ทดสอบบนเครื่องตัวเอง ไม่ต้องใช้ Cloud

### 2.1 ติดตั้งโปรแกรมที่ต้องใช้
- ติดตั้ง Node.js 24.16.0: โหลด https://nodejs.org หรือใช้ `nvm install 24.16.0 && nvm use 24.16.0`
- ติดตั้ง Python 3.12: https://www.python.org/downloads/
- ติดตั้ง Git: https://git-scm.com/download/win
- เช็ค: เปิด PowerShell พิมพ์ `node -v` ต้อง `v24.16.0`, `python --version`, `git --version` ต้องขึ้น

### 2.2 ติดตั้ง OpenClaw + Gateway
1. เปิด PowerShell **แบบ Admin** → รัน:
   ```powershell
   npm install -g openclaw@latest
   openclaw gateway install --port 18789 --token openclaw123 --force
   openclaw config set gateway.auth.token openclaw123
   openclaw gateway restart
   ```
2. เปิดโปรแกรม `OpenClaw Windows Companion` → จะเห็น `No gateway yet` → กด **`Direct`** (ไม่ใช่ Install) → ใส่:
   - `Gateway URL: ws://127.0.0.1:18789`
   - `Shared token: openclaw123`
   - `Name: My gateway` → `Save & connect`
   - ถ้าขึ้น `Awaiting approval` → เปิด PowerShell รัน `openclaw pairing approve line K4B8LECB` (โค้ดจะเปลี่ยนตามหน้าจอ) → กด `Connect` ใน Companion → ขึ้น `Connected`

### 2.3 รัน Webhook Local
1. โหลดโค้ด: `git clone https://github.com/kanchat-y/line-fb-webhook.git`
2. ติดตั้งไลบรารี:
   ```powershell
   cd line-fb-webhook
   pip install -r requirements.txt  # flask, line-bot-sdk, requests, gunicorn
   ```
3. ตั้งค่าตัวแปร (แก้เป็นค่าจริงของคุณ):
   ```powershell
   $env:LINE_CHANNEL_SECRET="843336fe6197dbb102465d974b862570"
   $env:LINE_CHANNEL_ACCESS_TOKEN="ZZtMaUZiLY1Ud6a+6ofbA/4wVTIslIzDNfGNa+5FyqWtHRmomUk/StGpbOIGdsD/4GzIDwYN9LiBeimd6h24tIeR/8I4QR/oQJzbWjxKaE6Y2agKKhw3rmaO2RbqqwZos53incopjnwIJY+3BFPSzwdB04t89/1O/w1cDnyilFU="
   $env:META_ACCESS_TOKEN="EAAY7hYjTZAXQBSbSiSf92yI205U1wpif8sOE20ag7Um1fW36nxNupv9KXFETWEHwsVluCk52CNZAnJTB865MJgiOYcKhn2mjreQSWdZBqJwDCmDgnVKQQFlXU30BpdSyN7Wx8GFY1BC3dZByFjLbYQ3MwxfGGeWPlOnqLRN6RcR5PewSsMYtHeyL9Y9m"
   python app.py  # จะรันที่ http://127.0.0.1:8080
   ```
   ต้องเห็น `Running on http://127.0.0.1:8080`

4. เปิด Tunnel ให้ LINE เรียกถึง:
   - โหลด cloudflared: https://github.com/cloudflare/cloudflared/releases → `cloudflared-windows-amd64.exe` → วางที่ `C:\Temp\`
   - เปิด PowerShell อีกอัน รัน:
     ```powershell
     .\cloudflared.exe tunnel --url http://127.0.0.1:8080
     ```
     จะได้ `https://xxx.trycloudflare.com` → เอา `https://xxx.trycloudflare.com/line-webhook` ไปใส่ LINE Developers → `Webhook URL` → `Verify` → `Success` → เปิด `Use webhook` = On

### 2.4 ทดสอบ Local
- เปิด LINE → แชท OA `ก๊อดเองแม่ตั้งให้` → ส่งรูป + พิมพ์ `สนามใหม่แมนยู สวยมาก โพสต์เลย ช่วยเกลาด้วย` → บอทตอบ Preview → พิมพ์ `ใช่` → โพสต์ลงเพจทันที
- เช็คที่ https://facebook.com/991675850550798

**ข้อจำกัด Local:** ต้องเปิดคอม + Flask + cloudflared ตลอด ปิดแล้ว LINE จะ `503` / URL tunnel เปลี่ยนทุกครั้งที่รันใหม่

---

## ส่วนที่ 3: แบบ Cloud = GitHub Cloud (แนะนำ ปิดคอมได้)

**เหมาะ:** ใช้งานจริง ไม่ต้องเปิดคอม 24 ชม.

### 3.1 Push โค้ดขึ้น GitHub (ครั้งเดียว)
1. มีโค้ดแล้วที่ `https://github.com/kanchat-y/line-fb-webhook` (ถ้ายังไม่มี สร้างตามนี้):
   ```powershell
   cd line-fb-webhook
   git init; git add .; git commit -m "initial webhook"
   git branch -M main
   git remote add origin https://ghp_...@github.com/kanchat-y/line-fb-webhook.git
   git push -u origin main
   ```
   - ต้องมีไฟล์ 5 อย่างใน repo: `app.py`, `requirements.txt`, `Procfile` (`web: gunicorn app:app`), `runtime.txt` (`python-3.12.7`), `README.md`

### 3.2 Deploy Render (ครั้งเดียว 2 นาที)
1. ไป https://dashboard.render.com → `New Web Service` → `Connect GitHub` → เลือก `kanchat-y/line-fb-webhook` → `Connect`
2. ตั้งค่า:
   - `Build Command`: `pip install -r requirements.txt`
   - `Start Command`: `gunicorn app:app`
   - `Environment` → `Add` 3 ตัว (วางค่าจริงที่ได้จาก 1.1 และ 1.2):
     - `LINE_CHANNEL_SECRET` = `843336fe6197dbb102465d974b862570`
     - `LINE_CHANNEL_ACCESS_TOKEN` = `ZZtMaUZiLY1Ud6a+6ofbA/4wVTIslIzDNfGNa+5FyqWtHRmomUk/StGpbOIGdsD/4GzIDwYN9LiBeimd6h24tIeR/8I4QR/oQJzbWjxKaE6Y2agKKhw3rmaO2RbqqwZos53incopjnwIJY+3BFPSzwdB04t89/1O/w1cDnyilFU=`
     - `META_ACCESS_TOKEN` = `EAAY7hYjTZAXQBSbSiSf92yI205U1wpif8sOE20ag7Um1fW36nxNupv9KXFETWEHwsVluCk52CNZAnJTB865MJgiOYcKhn2mjreQSWdZBqJwDCmDgnVKQQFlXU30BpdSyN7Wx8GFY1BC3dZByFjLbYQ3MwxfGGeWPlOnqLRN6RcR5PewSsMYtHeyL9Y9m` (อัน 60 วันเท่านั้น)
3. `Create Web Service` → รอ 1-2 นาที → สถานะ `Live` → จะได้ URL `https://line-fb-webhook.onrender.com`
   - ดู Logs ต้องเห็น `Listening at: http://0.0.0.0:10000` และ `Your service is live`

### 3.3 ตั้ง LINE Webhook ชี้ไป Cloud
- https://developers.line.biz → Channel `ก๊อดเองแม่ตั้งให้` → `Messaging API` → `Webhook URL`:
  ```
  https://line-fb-webhook.onrender.com/line-webhook
  ```
  → `Update` → `Verify` → ต้องขึ้น `Success` → เปิด `Use webhook` = **On**

### 3.4 กันหลับ 10 นาที (ฟรี)
- Render Free จะ sleep ถ้าไม่มีคนเข้า 15 นาที → LINE จะตอบช้า 30 วิ
- ไป https://cron-job.org → สร้างบัญชี → `Create cronjob` → `URL`: `https://line-fb-webhook.onrender.com/ping` → `Every 10 minutes` → `Create`
- หรือ https://uptimerobot.com ตั้งแบบเดียวกัน (อย่าใช้ `/line-webhook` ให้ใช้ `/ping`)

### 3.5 ทดสอบ Cloud (ปิดคอมได้เลย)
- ปิด PowerShell/Flask/cloudflared บนเครื่องได้เลย
- เปิด LINE → ส่งรูปสนามใหม่ + `สนามใหม่แมนยู อลังการสุดๆ 100,000 ที่นั่ง โพสต์เลย ช่วยเกลาด้วย` → บอทตอบ Preview → พิมพ์ `ใช่` → โพสต์ลงเพจทันที เช็คที่ https://facebook.com/991675850550798

---

## การใช้งาน LINE ประจำวัน (ใช้ได้ทั้ง 2 แบบ)

**ส่งใน LINE OA @308fvqux:**

| คุณทำ | บอททำ | คุณทำต่อ |
|-------|-------|----------|
| ส่งรูป + พิมพ์ `สนามใหม่แมนยู... โพสต์เลย ช่วยเกลาด้วย` | ตอบ `📋 Preview... 📸 มีรูป | ⚡ จะโพสต์ทันที` + `พิมพ์ ใช่ เพื่อยืนยัน` | พิมพ์ `ใช่` → โพสต์ทันที |
| ส่งข้อความอย่างเดียว ไม่มีรูป | ถาม `📸 ไม่เห็นรูป ต้องการรูปอะไร? 1.ส่งรูปมา 2.AI สร้าง 3.ข้อความล้วน` | เลือก 1/2/3 |
| พิมพ์ `ตั้งเวลา 19:45` หรือ `พรุ่งนี้ 09:00` | ตอบ `⏰ ตั้งเวลา 15/09 19:45` + Preview | `ใช่` → ตั้งเวลา (ต้องล่วงหน้า 10 นาที) |
| พิมพ์ `ช่วยเกลา` | แก้แคปชันเติม `#ก๊อดเองแม่ตั้งให้ #เรื่องทั่วไป` + อีโมจิ | `ใช่` |

**ตัวอย่างที่โพสต์สำเร็จแล้ว:**
- 15/09 15:18 สนามใหม่ 100k + รูป AI → `104158371681569_991786143873102` https://www.facebook.com/991675850550798/posts/991786143873102
- 15/09 17:33 Nike elite bag + รูป → `104158371681569_992225487162501`

---

## การต่ออายุ Token 60 วัน (ทำทุก 2 เดือน)

1. ไป https://developers.facebook.com/tools/explorer/?app_id=1754294572508532 → เลือก App → ติ๊ก 3 สิทธิ์ → `Generate Access Token` → Copy `EAAG...` (1 ชม.)
2. เปิดเบราว์เซอร์วาง:
   ```
   https://graph.facebook.com/oauth/access_token?grant_type=fb_exchange_token&client_id=1754294572508532&client_secret=a62b12021e733bfd1d38e2050a8bceee&fb_exchange_token=EAAG...
   ```
   เปลี่ยน `a62b...` (App Secret) และ `EAAG...` (อัน 1 ชม.) → Enter → จะได้ `EAAY...` 60 วัน
3. อัปเดต:
   - เครื่อง Local: `setx META_ACCESS_TOKEN "EAAY..."` → รีสตาร์ท `python app.py`
   - Cloud: Render → `line-fb-webhook` → `Environment` → แก้ `META_ACCESS_TOKEN` → `Save` → Deploy ใหม่

---

## ปัญหาที่พบบ่อย

| อาการ | สาเหตุ | แก้ |
|-------|--------|-----|
| LINE ตอบ `OpenClaw: access not configured` | ยังไม่ pairing | รัน `openclaw pairing approve line K4B8LECB` (โค้ดดูในแชท LINE) |
| LINE ตอบ `Authentication failed (401)` | LLM provider ไม่ได้ตั้งค่า (ถ้าใช้ OpenClaw LINE Channel) | เปลี่ยนมาใช้ Flask webhook ตรงแบบคู่มือนี้ (ไม่ต้องใช้ LLM) |
| LINE `503 Service Unavailable` | Flask/cloudflared ดับ หรือ tunnel เปลี่ยน URL | รัน `python app.py` + `cloudflared tunnel --url http://127.0.0.1:8080` ใหม่ แล้วอัปเดต Webhook URL |
| LINE Verify `405 Method Not Allowed` | ใส่ Webhook URL ผิด path | ต้องเป็น `https://xxx/line-webhook` (มี `-`) ไม่ใช่ `/` หรือ `/line/webhook` |
| LINE Verify `404 Not Found` | ใส่ URL ผิดหรือ Render ยังไม่ Live | เช็ค Render ว่า `Live` และ URL ถูก `https://line-fb-webhook.onrender.com/line-webhook` |
| Facebook `HTTP Error 400: Bad Request` | Token หมดอายุ (1 ชม.) หรือรูป catbox โหลดไม่ได้ | ใช้ Token 60 วัน + อัปโหลดรูปตรงแบบไฟล์ (แก้แล้วใน `app.py`) |
| `Session has expired` | Token หมดอายุ | เจน Token ใหม่ + แลก 60 วัน |
| คนอื่นดูโพสต์ใน Incognito ขึ้น `ไม่พร้อมใช้งาน` | App ยัง `In Development` | ไป `เผยแพร่` → สลับเป็น `Live` (ต้องกรอก Privacy Policy) |
| WSL `Node 22.22.3 is unsupported` | Companion พยายามใช้ Node 22 | ใช้ Gateway แบบ Windows `openclaw gateway install --port 18789` แทน WSL |

---

## ไฟล์สำคัญในเครื่อง

```
autopost/config.json - ตั้งค่า page_id 104158371681569
autopost/calendar.json - ปฏิทินโพสต์ทั้งหมด
autopost/media/*.jpg - รูปจาก LINE
autopost/line-webhook/app.py - Webhook หลัก
autopost/line-webhook/requirements.txt, Procfile, runtime.txt - สำหรับ Cloud
C:\Users\OMG\.openclaw\openclaw.json - Config OpenClaw Gateway
MANUAL.md - คู่มือฉบับย่อ
คู่มือมือใหม่-โพสต์ด้วยLINE-Facebook.md - ไฟล์นี้
autopost/setup-openclaw-local.ps1 - สคริปต์ติดตั้ง Local
autopost/setup-github-cloud.ps1 - สคริปต์ติดตั้ง Cloud
```

ทำตามคู่มือนี้ทีละขั้น ไม่เคยทำมาก่อนก็โพสต์ได้จริงทั้ง 2 แบบครับ
