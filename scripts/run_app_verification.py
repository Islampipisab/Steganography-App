import base64
import io
import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path
import sys

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from web.app import app


@dataclass
class TestResult:
    name: str
    ok: bool
    elapsed_ms: int
    detail: str = ""


def make_png_bytes(width=256, height=256, color=(120, 140, 160)):
    img = Image.new("RGB", (width, height), color)
    b = io.BytesIO()
    img.save(b, format="PNG")
    return b.getvalue()


def make_barcode_png(client, text):
    r = client.post("/api/encode", data={"text": text, "use_hybrid": "0"})
    if r.status_code != 200:
        raise RuntimeError(f"/api/encode failed: {r.status_code} {r.data[:200]!r}")
    return r.data


def post_multipart(client, url, data):
    return client.post(url, data=data, content_type="multipart/form-data")


def run():
    results = []
    c = app.test_client()

    # 1) Encode/decode direct barcode
    t0 = time.time()
    name = "encode_decode_text"
    try:
        barcode = make_barcode_png(c, "Doctor demo verification text")
        r = post_multipart(c, "/api/decode", {"barcode": (io.BytesIO(barcode), "barcode.png")})
        j = r.get_json(silent=True) or {}
        ok = r.status_code == 200 and "Doctor demo verification text" in (j.get("text") or "")
        detail = j.get("error", "") if not ok else "decoded expected text"
        results.append(TestResult(name, ok, int((time.time() - t0) * 1000), detail))
    except Exception as e:
        results.append(TestResult(name, False, int((time.time() - t0) * 1000), str(e)))

    # 2) Hide/extract text for methods
    for method in ("LSB", "DCT", "Hybrid"):
        t0 = time.time()
        name = f"hide_extract_text_{method.lower()}"
        try:
            msg = f"extract text check {method}"
            cover = make_png_bytes(320, 320, (90, 110, 130))
            r_hide = post_multipart(
                c,
                "/api/hide-text",
                {
                    "text": msg,
                    "method": method,
                    "cover": (io.BytesIO(cover), "cover.png"),
                },
            )
            if r_hide.status_code != 200:
                raise RuntimeError(f"/api/hide-text {method} failed: {r_hide.status_code}")
            stego = r_hide.data
            r_ext = post_multipart(
                c,
                "/api/extract-text",
                {
                    "method": method,
                    "stego": (io.BytesIO(stego), "stego.png"),
                },
            )
            j = r_ext.get_json(silent=True) or {}
            ok = r_ext.status_code == 200 and msg in (j.get("text") or "")
            detail = j.get("error", "") if not ok else "roundtrip ok"
            results.append(TestResult(name, ok, int((time.time() - t0) * 1000), detail))
        except Exception as e:
            results.append(TestResult(name, False, int((time.time() - t0) * 1000), str(e)))

    # 3) Hide/extract barcode decode for methods
    for method in ("LSB", "DCT", "Hybrid"):
        t0 = time.time()
        name = f"hide_extract_barcode_{method.lower()}"
        try:
            msg = f"barcode extraction check {method}"
            barcode = make_barcode_png(c, msg)
            cover = make_png_bytes(384, 384, (100, 120, 140))
            r_hide = post_multipart(
                c,
                "/api/hide-barcode?format=json",
                {
                    "method": method,
                    "jpeg_robust": "0",
                    "barcode": (io.BytesIO(barcode), "barcode.png"),
                    "cover": (io.BytesIO(cover), "cover.png"),
                },
            )
            j_hide = r_hide.get_json(silent=True) or {}
            if r_hide.status_code != 200:
                raise RuntimeError(j_hide.get("error", f"/api/hide-barcode {method} failed"))
            stego_b64 = j_hide.get("stego_b64")
            if not stego_b64:
                raise RuntimeError("missing stego_b64")
            stego = base64.b64decode(stego_b64)
            r_ext = post_multipart(
                c,
                "/api/extract-barcode",
                {
                    "method": method,
                    "stego": (io.BytesIO(stego), "stego.png"),
                },
            )
            j = r_ext.get_json(silent=True) or {}
            ok = r_ext.status_code == 200 and msg in (j.get("text") or "")
            detail = j.get("error", "") if not ok else "roundtrip ok"
            results.append(TestResult(name, ok, int((time.time() - t0) * 1000), detail))
        except Exception as e:
            results.append(TestResult(name, False, int((time.time() - t0) * 1000), str(e)))

    # 4) Stress extraction repeat to catch intermittent failures
    t0 = time.time()
    name = "repeat_extract_barcode_lsb_20x"
    try:
        msg = "intermittent fetch/extract stress test"
        barcode = make_barcode_png(c, msg)
        cover = make_png_bytes(384, 384, (111, 133, 155))
        r_hide = post_multipart(
            c,
            "/api/hide-barcode?format=json",
            {
                "method": "LSB",
                "jpeg_robust": "0",
                "barcode": (io.BytesIO(barcode), "barcode.png"),
                "cover": (io.BytesIO(cover), "cover.png"),
            },
        )
        j_hide = r_hide.get_json(silent=True) or {}
        if r_hide.status_code != 200:
            raise RuntimeError(j_hide.get("error", "/api/hide-barcode failed"))
        stego = base64.b64decode(j_hide["stego_b64"])

        failures = []
        for i in range(20):
            r_ext = post_multipart(
                c,
                "/api/extract-barcode",
                {"method": "LSB", "stego": (io.BytesIO(stego), f"stego_{i}.png")},
            )
            j = r_ext.get_json(silent=True) or {}
            if not (r_ext.status_code == 200 and msg in (j.get("text") or "")):
                failures.append({"iter": i + 1, "status": r_ext.status_code, "error": j.get("error", "unknown")})

        ok = len(failures) == 0
        detail = "20/20 successful" if ok else f"failures: {failures[:3]}"
        results.append(TestResult(name, ok, int((time.time() - t0) * 1000), detail))
    except Exception as e:
        results.append(TestResult(name, False, int((time.time() - t0) * 1000), str(e)))

    # 5) Metrics API sanity
    t0 = time.time()
    name = "metrics_api"
    try:
        orig = make_png_bytes(256, 256, (100, 120, 140))
        stego = make_png_bytes(256, 256, (101, 120, 140))
        r = post_multipart(
            c,
            "/api/metrics",
            {"original": (io.BytesIO(orig), "orig.png"), "stego": (io.BytesIO(stego), "stego.png")},
        )
        j = r.get_json(silent=True) or {}
        ok = r.status_code == 200 and all(k in j for k in ("PSNR", "SSIM", "BER"))
        detail = "metrics keys present" if ok else j.get("error", "missing metrics")
        results.append(TestResult(name, ok, int((time.time() - t0) * 1000), detail))
    except Exception as e:
        results.append(TestResult(name, False, int((time.time() - t0) * 1000), str(e)))

    summary = {
        "total": len(results),
        "passed": sum(1 for r in results if r.ok),
        "failed": sum(1 for r in results if not r.ok),
        "results": [asdict(r) for r in results],
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    run()

