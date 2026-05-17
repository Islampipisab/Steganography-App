import io
import base64
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from web.app import app


barcode_path = Path(
    r"C:\Users\pipis\.cursor\projects\c-Users-pipis-OneDrive-Desktop-newgrad\assets\c__Users_pipis_AppData_Roaming_Cursor_User_workspaceStorage_73701bacba3b1b782b5361dccfd68ec7_images_barcode__21_-73b00ece-8f1f-4419-a3b7-4bf931c73dca.png"
)
cover_path = Path(
    r"C:\Users\pipis\.cursor\projects\c-Users-pipis-OneDrive-Desktop-newgrad\assets\c__Users_pipis_AppData_Roaming_Cursor_User_workspaceStorage_73701bacba3b1b782b5361dccfd68ec7_images_Luxury_Watches-43718099-600b-4496-a4af-92bef3fffa64.png"
)
out_stego = Path(r"C:\Users\pipis\Downloads\stego_from_user_inputs.png")
out_extracted_barcode = Path(r"C:\Users\pipis\Downloads\extracted_barcode_from_stego.png")
out_extract_json = Path(r"C:\Users\pipis\Downloads\extract_result_from_stego.json")

c = app.test_client()

with open(barcode_path, "rb") as bf, open(cover_path, "rb") as cf:
    r = c.post(
        "/api/hide-barcode?format=json",
        data={
            "method": "LSB",
            "jpeg_robust": "0",
            "barcode": (io.BytesIO(bf.read()), barcode_path.name),
            "cover": (io.BytesIO(cf.read()), cover_path.name),
        },
        content_type="multipart/form-data",
    )

print("hide status:", r.status_code)
j = r.get_json(silent=True) or {}
if r.status_code != 200:
    print("hide error:", j.get("error"))
    raise SystemExit(1)

stego_bytes = base64.b64decode(j["stego_b64"])
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
    raise SystemExit(2)

if j2.get("barcode_b64"):
    out_extracted_barcode.write_bytes(base64.b64decode(j2["barcode_b64"]))
    print("saved extracted barcode:", out_extracted_barcode)

print("text snippet:", (j2.get("text") or "")[:200])
print("log:", j2.get("log"))

