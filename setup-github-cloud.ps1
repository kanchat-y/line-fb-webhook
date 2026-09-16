# Setup Cloud Server (Render) - ครั้งเดียวจบ ปิดคอมได้
# 1. Push ขึ้น GitHub (ทำแล้ว): https://github.com/kanchat-y/line-fb-webhook
# 2. Render: https://dashboard.render.com → New Web Service → Connect kanchat-y/line-fb-webhook
#    Build: pip install -r requirements.txt
#    Start: gunicorn app:app
#    Env: LINE_CHANNEL_SECRET, LINE_CHANNEL_ACCESS_TOKEN, META_ACCESS_TOKEN (อัน 60 วัน)
# 3. LINE Webhook: https://line-fb-webhook.onrender.com/line-webhook → Verify
# 4. กันหลับ: https://cron-job.org → https://line-fb-webhook.onrender.com/ping ทุก 10 นาที

# ต่ออายุ Token 60 วันทุก 2 เดือน:
# 1. https://developers.facebook.com/tools/explorer/?app_id=1754294572508532 → Generate EAAG... (1 ชม.)
# 2. แลก 60 วัน:
# https://graph.facebook.com/oauth/access_token?grant_type=fb_exchange_token&client_id=1754294572508532&client_secret=a62b12021e733bfd1d38e2050a8bceee&fb_exchange_token=EAAG...
# 3. ได้ EAAY... 60 วัน → setx META_ACCESS_TOKEN "EAAY..." + Render → Environment → แก้ META_ACCESS_TOKEN → Save
