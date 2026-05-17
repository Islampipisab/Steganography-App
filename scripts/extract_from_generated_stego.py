import io
import base64
import json
import re
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from web.app import app

stego_path = Path(r"C:\Users\pipis\Downloads\watch_with_hidden_barcode_lsb.png")
out_extracted_barcode = Path(r"C:\Users\pipis\Downloads\extracted_barcode_from_watch_stego.png")
out_extracted_text_json = Path(r"C:\Users\pipis\Downloads\extracted_text_result_from_watch_stego.json")
out_recovered_image = Path(r"C:\Users\pipis\Downloads\recovered_comments_image_from_stego.png")

client = app.test_client()

# 1) Extract barcode from stego
r = client.post(
    "/api/extract-barcode",
    data={"method": "LSB", "stego": (io.BytesIO(stego_path.read_bytes()), stego_path.name)},
    content_type="multipart/form-data",
)
j = r.get_json(silent=True) or {}
if r.status_code != 200:
    raise RuntimeError(f"extract-barcode failed: {j.get('error', r.status_code)}")

if j.get("barcode_b64"):
    out_extracted_barcode.write_bytes(base64.b64decode(j["barcode_b64"]))

# save extract JSON details
out_extracted_text_json.write_text(json.dumps(j, indent=2), encoding="utf-8")

# 2) Recover original image from extracted text payload
text = j.get("text", "")
if text.startswith("[IMAGE:"):
    header_end = text.find("]")
    if header_end != -1:
        encoded = text[header_end + 1 :].strip()
        encoded = re.sub(r"[^A-Za-z0-9+/=]", "", encoded)
        data = base64.b64decode(encoded)
        out_recovered_image.write_bytes(data)

print(str(out_extracted_barcode))
print(str(out_recovered_image))
print(str(out_extracted_text_json))

