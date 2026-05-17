import io
import base64
import json
from pathlib import Path
import sys
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from web.app import app

watch_path = Path(
    r"C:\Users\pipis\.cursor\projects\c-Users-pipis-OneDrive-Desktop-newgrad\assets\c__Users_pipis_AppData_Roaming_Cursor_User_workspaceStorage_73701bacba3b1b782b5361dccfd68ec7_images_Luxury_Watches-43718099-600b-4496-a4af-92bef3fffa64.png"
)
cover_path = watch_path

out_barcode = Path(r"C:\Users\pipis\Downloads\barcode_valid_from_watch.png")
out_stego = Path(r"C:\Users\pipis\Downloads\stego_valid_from_watch.png")
out_extracted_barcode = Path(r"C:\Users\pipis\Downloads\extracted_barcode_valid_from_stego.png")
out_extract_json = Path(r"C:\Users\pipis\Downloads\extract_valid_result.json")

c = app.test_client()

img = Image.open(watch_path)
fmt = (img.format or "PNG").upper()
w, h = img.size
img_b64 = base64.b64encode(watch_path.read_bytes()).decode("utf-8")
text = f"[IMAGE:{watch_path.name}:{fmt}:{w}x{h}]\\n{img_b64}"

r0 = c.post("/api/encode", data={"text": text, "use_hybrid": "0"})
print("encode status:", r0.status_code)
if r0.status_code != 200:
    print((r0.get_json(silent=True) or {}).get("error"))
    raise SystemExit(1)

barcode_bytes = r0.data
out_barcode.write_bytes(barcode_bytes)
print("saved valid barcode:", out_barcode)

with open(cover_path, "rb") as cf:
    r1 = c.post(
        "/api/hide-barcode?format=json",
        data={
            "method": "LSB",
            "jpeg_robust": "0",
            "barcode": (io.BytesIO(barcode_bytes), out_barcode.name),
            "cover": (io.BytesIO(cf.read()), cover_path.name),
        },
        content_type="multipart/form-data",
    )

print("hide status:", r1.status_code)
j1 = r1.get_json(silent=True) or {}
if r1.status_code != 200:
    print("hide error:", j1.get("error"))
    raise SystemExit(2)

stego_bytes = base64.b64decode(j1["stego_b64"])
out_stego.write_bytes(stego_bytes)
print("saved stego:", out_stego)

r2 = c.post(
    "/api/extract-barcode",
    data={"method": "LSB", "stego": (io.BytesIO(stego_bytes), out_stego.name)},
    content_type="multipart/form-data",
)
print("extract status:", r2.status_code)
j2 = r2.get_json(silent=True) or {}
out_extract_json.write_text(json.dumps(j2, indent=2), encoding="utf-8")
if r2.status_code != 200:
    print("extract error:", j2.get("error"))
    raise SystemExit(3)

if j2.get("barcode_b64"):
    out_extracted_barcode.write_bytes(base64.b64decode(j2["barcode_b64"]))
    print("saved extracted barcode:", out_extracted_barcode)

print("text prefix:", (j2.get("text") or "")[:120])
print("log:", j2.get("log"))

