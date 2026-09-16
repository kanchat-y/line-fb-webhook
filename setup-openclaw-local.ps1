# Setup Local Server - รันครั้งเดียว
# ใช้ Node 24.16.0 + Python 3.12
nvm install 24.16.0; nvm use 24.16.0
npm install -g openclaw@latest
pip install flask line-bot-sdk requests gunicorn

# Gateway
openclaw gateway install --port 18789 --token openclaw123 --force
openclaw config set gateway.auth.token openclaw123
openclaw gateway restart

# LINE Channel (ใส่ค่าจริงก่อนรัน)
# openclaw channels add --channel line --channel-secret 843336fe6197dbb102465d974b862570 --channel-access-token ZZtMaUZ...

# Facebook Token
setx META_ACCESS_TOKEN "EAAY7hYjTZAXQBSbSiSf92yI205U1wpif8sOE20ag7Um1fW36nxNupv9KXFETWEHwsVluCk52CNZAnJTB865MJgiOYcKhn2mjreQSWdZBqJwDCmDgnVKQQFlXU30BpdSyN7Wx8GFY1BC3dZByFjLbYQ3MwxfGGeWPlOnqLRN6RcR5PewSsMYtHeyL9Y9m"

# Webhook Local
$env:LINE_CHANNEL_SECRET="843336fe6197dbb102465d974b862570"
$env:LINE_CHANNEL_ACCESS_TOKEN="ZZtMaUZiLY1Ud6a+6ofbA/4wVTIslIzDNfGNa+5FyqWtHRmomUk/StGpbOIGdsD/4GzIDwYN9LiBeimd6h24tIeR/8I4QR/oQJzbWjxKaE6Y2agKKhw3rmaO2RbqqwZos53incopjnwIJY+3BFPSzwdB04t89/1O/w1cDnyilFU="
$env:META_ACCESS_TOKEN="EAAY7hYjTZAXQBSbSiSf92yI205U1wpif8sOE20ag7Um1fW36nxNupv9KXFETWEHwsVluCk52CNZAnJTB865MJgiOYcKhn2mjreQSWdZBqJwDCmDgnVKQQFlXU30BpdSyN7Wx8GFY1BC3dZByFjLbYQ3MwxfGGeWPlOnqLRN6RcR5PewSsMYtHeyL9Y9m"
python autopost/line-webhook/app.py

# เปิดอีก PowerShell: cloudflared tunnel --url http://127.0.0.1:8080
# เอา https://xxx.trycloudflare.com/line-webhook ไปใส่ LINE Developers → Verify
