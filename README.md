# LINE → Facebook AutoPost

ส่งไอเดีย+รูปทาง LINE แล้วโพสต์ลงเพจ **ก๊อดเองแม่ตั้งให้ (104158371681569)** ทันทีหรือตั้งเวลา

## วิธีทำงาน
```
LINE (พิมพ์ + ส่งรูป) → Webhook (app.py) → Facebook Graph API → เพจ
                           ↓
                    calendar.json + media/
```

## คำสั่งใน LINE
- `สวัสดีครับ ทริปใหม่เกียวโต 5 วัน 4 คืน #เที่ยวญี่ปุ่น โพสต์เลย` → โพสต์ทันที
- `แมนยูคืนนี้วิเคราะห์ก่อนเกม ตั้งเวลา 19:45` → ตั้งเวลา 19:45 วันนี้
- `พรุ่งนี้ 9 โมง โปรโมชัน...` → ตั้งพรุ่งนี้ 09:00
- ส่งรูปอย่างเดียว → บอทตอบ "รับรูปแล้ว ส่งแคปชันมา"
- ส่งรูป + แคปชันในข้อความเดียว → โพสต์พร้อมรูปทันที

## ติดตั้ง (10 นาที)

### 1. สร้าง LINE Official Account
- https://developers.line.biz/ → Create Provider → Create Channel (Messaging API)
- Copy `Channel Secret` และ `Channel Access Token (long-lived)`

### 2. ตั้งค่าเซิร์ฟเวอร์
```powershell
pip install flask line-bot-sdk
$env:LINE_CHANNEL_SECRET="..."
$env:LINE_CHANNEL_ACCESS_TOKEN="..."
$env:META_ACCESS_TOKEN="EAAY..."  # อันที่ใช้กับเพจ 104158371681569 อยู่แล้ว
python autopost/line-webhook/app.py  # รันที่ :8080
```
ต้องมีโดเมน HTTPS สำหรับ Webhook (ใช้ ngrok ทดสอบ: `ngrok http 8080`)

### 3. ตั้ง Webhook ใน LINE Developers
- Channel → Messaging API → Webhook URL: `https://your-domain/line-webhook`
- เปิด `Use webhook` + ปิด `Auto-reply` + เปิด `Greeting off` (ให้บอทตอบเอง)

### ทางเลือก: ใช้ OpenClaw LINE Channel โดยตรง (ไม่ต้องรัน Flask)
```powershell
openclaw channels add --channel line --token $LINE_CHANNEL_ACCESS_TOKEN
# แล้วตั้ง automation:
openclaw cron add line-autopost --schedule "* * * * *" --prompt "เช็คข้อความ LINE ล่าสุด ถ้ามีรูป+ข้อความให้โพสต์ลงเพจ 104158371681569 ทันทีหรือตามเวลาที่ระบุ"
```
OpenClaw Gateway จะรับ LINE ให้เอง แล้ว agent จะเรียก `post_to_facebook` ให้

## ทดสอบ
1. แอด LINE OA เป็นเพื่อน
2. ส่งข้อความ `ทดสอบระบบ โพสต์เลย`
3. ดูในเพจ https://facebook.com/991675850550798

## ความปลอดภัย
- ล็อกเพจเดียว `104158371681569` เท่านั้น (แก้ PAGE_ID ใน app.py)
- รูปจาก LINE จะถูกดาวน์โหลดมา `autopost/media/` แล้วอัปโหลดไป hosting ก่อนโพสต์
- ต้องตั้งเวลาล่วงหน้า 10 นาที (Facebook บังคับ)

## ไฟล์
- `app.py` - Webhook หลัก
- `../calendar.json` - log ทุกโพสต์
- `../media/` - เก็บรูปจาก LINE
