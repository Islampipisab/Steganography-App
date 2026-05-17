import io
import base64
from pathlib import Path
import sys
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from web.app import app

payload_img = Path(
    r"C:\Users\pipis\.cursor\projects\c-Users-pipis-OneDrive-Desktop-newgrad\assets\c__Users_pipis_AppData_Roaming_Cursor_User_workspaceStorage_73701bacba3b1b782b5361dccfd68ec7_images_WhatsApp_Image_2025-11-25_at_4.25.30_PM-67ae3b10-27b2-4859-a6d9-e8c490a1d2f2.png"
)
cover_img = Path(
    r"C:\Users\pipis\.cursor\projects\c-Users-pipis-OneDrive-Desktop-newgrad\assets\c__Users_pipis_AppData_Roaming_Cursor_User_workspaceStorage_73701bacba3b1b782b5361dccfd68ec7_images_Luxury_Watches-43718099-600b-4496-a4af-92bef3fffa64.png"
)

out_barcode = Path(r"C:\Users\pipis\Downloads\barcode_from_comments_image.png")
out_stego = Path(r"C:\Users\pipis\Downloads\watch_with_hidden_barcode_lsb.png")

client = app.test_client()

# Build [IMAGE:..]\nbase64 payload same as UI behavior.
img = Image.open(payload_img)
fmt = (img.format or "PNG").upper()
w, h = img.size
payload_b64 = base64.b64encode(payload_img.read_bytes()).decode("utf-8")
text = f"[IMAGE:{payload_img.name}:{fmt}:{w}x{h}]\\n{payload_b64}"

# Encode to barcode
r_encode = client.post("/api/encode", data={"text": text, "use_hybrid": "0"})
if r_encode.status_code != 200:
    raise RuntimeError(f"Encode failed: {r_encode.status_code} {r_encode.get_data(as_text=True)[:500]}")
barcode_bytes = r_encode.data
out_barcode.write_bytes(barcode_bytes)

# Hide barcode in watch using LSB
with open(cover_img, "rb") as cf:
    r_hide = client.post(
        "/api/hide-barcode?format=json",
        data={
            "method": "LSB",
            "jpeg_robust": "0",
            "barcode": (io.BytesIO(barcode_bytes), out_barcode.name),
            "cover": (io.BytesIO(cf.read()), cover_img.name),
        },
        content_type="multipart/form-data",
    )

if r_hide.status_code != 200:
    j = r_hide.get_json(silent=True) or {}
    raise RuntimeError(f"Hide failed: {j.get('error', r_hide.status_code)}")

j = r_hide.get_json()
stego_bytes = base64.b64decode(j["stego_b64"])
out_stego.write_bytes(stego_bytes)

print(str(out_barcode))
print(str(out_stego))

