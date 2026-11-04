# -*- coding: utf-8 -*-
"""เรียก gemini_caption_from_images จริงจาก app.py กับรูปจริง"""
import os, sys, importlib.util

os.environ["LINE_CHANNEL_SECRET"] = "test-secret-0123456789abcdef0123456789abcdef"
os.environ.setdefault("LINE_CHANNEL_ACCESS_TOKEN", "test-token")
os.environ.setdefault("FORCE_PAGE_ID", "788732444316483")
assert os.environ.get("GEMINI_API_KEY"), "ต้องมี GEMINI_API_KEY"

here = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("app_real", os.path.join(here, "app.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

img = r"C:\Users\OMG\Documents\Default Project\post-hatyai-park-2floor.jpg"
if not os.path.exists(img):
    img = r"C:\Users\OMG\Documents\Default Project\bodybuilder-bg.jpg"

caption, err = m.gemini_caption_from_images([img], "")
print("err:", repr(err))
print("=== CAPTION ===")
print(caption)
print("=== STATS ===")
lines = [l for l in caption.splitlines() if l.strip()]
print("non-empty lines:", len(lines))
print("hashtags:", caption.count("#"))
print("has link:", "http" in caption)

ok = bool(caption) and not err
ok = ok and 1 <= len(lines) <= 6
ok = ok and caption.count("#") >= 3
ok = ok and "http" not in caption
print("\nRESULT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
