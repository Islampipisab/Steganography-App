#!/usr/bin/env python3
"""
Steganography System - Web application.
Run from stego_project: python web/app.py  or  flask --app web.app run
"""
import os
import sys
import io
import json
import base64
import re
import tempfile
import time

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, request, jsonify, send_file, render_template

from config.settings import MAX_IMAGE_PIXELS, HYBRID_LSB_RATIO
from core import BarcodeSteganography, DCTSteganography, HybridSteganography
from crypto import HybridCrypto
from barcode import CustomBarcodeSteganography
from metrics import QualityMetrics
from processing import apply_median_filter, apply_gaussian_filter
from PIL import Image
import numpy as np

Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

app = Flask(__name__, template_folder="templates", static_folder="static")
# Allow large cover/barcode uploads (e.g. for "expand barcode to fill cover"). If using nginx, set client_max_body_size.
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024  # 200 MB


@app.after_request
def _expose_api_headers(response):
    """Let browsers read custom headers on API responses (needed for some mobile/CORS setups)."""
    if request.path.startswith("/api/"):
        response.headers["Access-Control-Expose-Headers"] = "X-Progress-Log, X-Metrics-Json, X-Timings-Json"
    return response

_cbs = None
_dct_stego = None
_dct_stego_jpeg = None
_hybrid_stego = None
_barcode_stego = None


def get_cbs():
    global _cbs
    if _cbs is None:
        _cbs = CustomBarcodeSteganography()
        try:
            if os.path.exists("private_key.pem") and os.path.exists("public_key.pem"):
                priv, pub = HybridCrypto.load_rsa_keys()
                _cbs.hybrid_crypto = HybridCrypto(rsa_public_key=pub, rsa_private_key=priv)
            else:
                _cbs.hybrid_crypto = HybridCrypto()
                _cbs.hybrid_crypto.save_rsa_keys()
        except Exception:
            _cbs.hybrid_crypto = HybridCrypto()
    return _cbs


def get_dct():
    global _dct_stego
    if _dct_stego is None:
        _dct_stego = DCTSteganography()
    return _dct_stego


def get_dct_jpeg():
    global _dct_stego_jpeg
    if _dct_stego_jpeg is None:
        _dct_stego_jpeg = DCTSteganography(jpeg_robust_mode=True)
    return _dct_stego_jpeg


def get_hybrid():
    global _hybrid_stego
    if _hybrid_stego is None:
        _hybrid_stego = HybridSteganography()
    return _hybrid_stego


def get_barcode_stego():
    global _barcode_stego
    if _barcode_stego is None:
        _barcode_stego = BarcodeSteganography()
    return _barcode_stego


def _barcode_pattern_to_bytes(pattern, scale=10):
    scaled = np.repeat(np.repeat(pattern, scale, axis=0), scale, axis=1)
    scaled = (scaled * 85).clip(0, 255).astype(np.uint8)
    img = Image.fromarray(scaled, mode="L")
    buf = io.BytesIO()
    img.save(buf, "PNG", compress_level=0)
    buf.seek(0)
    return buf


def _get_upload_path(key, allowed=None):
    f = request.files.get(key)
    if not f or f.filename == "":
        return None
    if allowed and f.filename and not any(f.filename.lower().endswith(ext) for ext in allowed):
        return None
    return f


def _to_jsonable(value):
    """Recursively convert numpy/scalar values into JSON-serializable Python types."""
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(v) for v in value]
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    return value


def _barcode_header_bits():
    """Bits used by LSB/DCT/Hybrid barcode header: magic(8) + height(16) + width(16) + scale(8)."""
    return 8 * 8 + 16 + 16 + 8


def _scale_barcode_pattern_to_fill_cover(pattern, cover_path, method, jpeg_robust=False):
    """Scale barcode pattern up so it uses the cover capacity (expand barcode to fill cover)."""
    cover_img = Image.open(cover_path).convert("RGB")
    width, height = cover_img.size  # PIL Image uses (width, height)
    channels = 3
    Bh, Bw = pattern.shape
    header_bits = _barcode_header_bits()
    pattern_bits = Bh * Bw * 2

    if method == "LSB":
        capacity = height * width * channels
    elif method == "DCT":
        block_size = 8
        blocks_per_row = width // block_size
        blocks_per_col = height // block_size
        bits_per_block = 8 if not jpeg_robust else 3
        capacity = blocks_per_row * blocks_per_col * bits_per_block * channels
    else:
        # Hybrid: LSB gets lsb_ratio of bits, DCT gets the rest.
        lsb_capacity = height * width
        blocks_per_row = width // 8
        blocks_per_col = height // 8
        bits_per_block = 8
        dct_capacity = blocks_per_row * blocks_per_col * bits_per_block * 2
        capacity = int(min(lsb_capacity / HYBRID_LSB_RATIO, dct_capacity / (1 - HYBRID_LSB_RATIO)))

    if capacity <= header_bits + pattern_bits:
        return pattern
    # Performance guard: for already-large barcodes (common with image payloads),
    # avoid aggressive upscaling which can cause very long embed times.
    if pattern_bits >= int(capacity * 0.25):
        return pattern
    if Bh * Bw >= 300000:
        return pattern
    max_pattern_bits = capacity - header_bits
    if max_pattern_bits <= 0:
        return pattern
    # k such that (Bh*k)*(Bw*k)*2 <= max_pattern_bits  =>  k^2 <= max_pattern_bits / (2*Bh*Bw)
    k_sq = max_pattern_bits / (2.0 * Bh * Bw)
    k = int(k_sq ** 0.5)
    if k <= 1:
        return pattern
    # Cap to avoid huge arrays (e.g. 4096 max dimension)
    max_side = 4096
    k = min(k, max_side // Bh, max_side // Bw)
    if k <= 1:
        return pattern
    # Keep expansion moderate to prevent request stalls on large payloads.
    k = min(k, 4)
    scaled = pattern.repeat(k, axis=0).repeat(k, axis=1)
    return np.asarray(scaled, dtype=np.uint8)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/encode", methods=["POST"])
def api_encode():
    total_start = time.perf_counter()
    text = request.form.get("text", "").strip()
    use_hybrid = request.form.get("use_hybrid", "0") == "1"
    if not text:
        return jsonify({"error": "No text provided"}), 400
    log = []
    try:
        log.append("10% – Loading encoder")
        encode_start = time.perf_counter()
        cbs = get_cbs()
        log.append("40% – Encoding to barcode pattern")
        pattern = cbs.encode(text, use_hybrid_encryption=use_hybrid)
        encode_time = time.perf_counter() - encode_start
        log.append("80% – Rendering PNG")
        render_start = time.perf_counter()
        buf = _barcode_pattern_to_bytes(pattern)
        render_time = time.perf_counter() - render_start
        total_time = time.perf_counter() - total_start
        timings = {
            "encode": encode_time,
            "preview_render": render_time,
            "total": total_time,
        }
        log.append(f"Timing - Encode: {encode_time:.3f}s")
        log.append(f"Timing - Render PNG: {render_time:.3f}s")
        log.append(f"Timing - Total: {total_time:.3f}s")
        log.append("100% – Done")
        resp = send_file(buf, mimetype="image/png", as_attachment=True, download_name="barcode.png")
        resp.headers["X-Progress-Log"] = json.dumps(log)
        resp.headers["X-Timings-Json"] = json.dumps(timings)
        return resp
    except Exception as e:
        return jsonify({"error": str(e), "log": log}), 500


@app.route("/api/decode", methods=["POST"])
def api_decode():
    total_start = time.perf_counter()
    f = _get_upload_path("barcode", (".png", ".bmp", ".jpg", ".jpeg"))
    if not f:
        return jsonify({"error": "No barcode image provided"}), 400
    log = []
    try:
        path = tempfile.mktemp(suffix=".png")
        upload_start = time.perf_counter()
        f.save(path)
        upload_time = time.perf_counter() - upload_start
        try:
            log.append("25% – Loading barcode image")
            cbs = get_cbs()
            load_start = time.perf_counter()
            pattern = cbs.load_barcode(path)
            load_time = time.perf_counter() - load_start
            log.append("60% – Decoding pattern")
            decode_start = time.perf_counter()
            text = cbs.decode(pattern, use_hybrid_decryption=True)
            decode_time = time.perf_counter() - decode_start
            log.append("90% – Parsing result")
            parse_start = time.perf_counter()
            if text.startswith("[IMAGE:") and "[HYBRID_ENCRYPTED" not in text and "[BLOCK_ENC:" not in text:
                header_end = text.find("]")
                if header_end != -1:
                    encoded = text[header_end + 1:].strip()
                    encoded = re.sub(r"[^A-Za-z0-9+/=]", "", encoded)
                    try:
                        data = base64.b64decode(encoded)
                        img_b64 = base64.b64encode(data).decode("utf-8")
                        parse_time = time.perf_counter() - parse_start
                        total_time = time.perf_counter() - total_start
                        timings = {
                            "upload": upload_time,
                            "load": load_time,
                            "decode_payload": decode_time,
                            "image_parse": parse_time,
                            "total": total_time,
                        }
                        log.append(f"Timing - Upload: {upload_time:.3f}s")
                        log.append(f"Timing - Load barcode: {load_time:.3f}s")
                        log.append(f"Timing - Decode payload: {decode_time:.3f}s")
                        log.append(f"Timing - Image parse: {parse_time:.3f}s")
                        log.append(f"Timing - Total: {total_time:.3f}s")
                        log.append("100% – Done")
                        return jsonify({"text": text[:header_end + 1], "is_image": True, "image_b64": img_b64, "log": log, "progress": 100, "timings": timings})
                    except Exception:
                        pass
            parse_time = time.perf_counter() - parse_start
            total_time = time.perf_counter() - total_start
            timings = {
                "upload": upload_time,
                "load": load_time,
                "decode_payload": decode_time,
                "parse": parse_time,
                "total": total_time,
            }
            log.append(f"Timing - Upload: {upload_time:.3f}s")
            log.append(f"Timing - Load barcode: {load_time:.3f}s")
            log.append(f"Timing - Decode payload: {decode_time:.3f}s")
            log.append(f"Timing - Parse: {parse_time:.3f}s")
            log.append(f"Timing - Total: {total_time:.3f}s")
            log.append("100% – Done")
            return jsonify({"text": text, "is_image": False, "log": log, "progress": 100, "timings": timings})
        finally:
            try:
                os.unlink(path)
            except Exception:
                pass
    except Exception as e:
        return jsonify({"error": str(e), "log": log}), 500


def _run_hide(cover_path, out_path, method, text=None, barcode_path=None, jpeg_robust=False):
    """Run hide-text or hide-barcode; write result to out_path. Returns None on success, error string on failure."""
    try:
        if text is not None:
            if method == "LSB":
                get_cbs().hide_text_directly(text, cover_path, out_path)
            elif method == "DCT":
                get_dct().hide_text_dct(cover_path, text, out_path)
            else:
                get_hybrid().hide_text_hybrid(cover_path, text, out_path)
        else:
            pattern = get_cbs().load_barcode(barcode_path)
            pattern = _scale_barcode_pattern_to_fill_cover(
                pattern, cover_path, method, jpeg_robust
            )
            if method == "LSB":
                get_barcode_stego().hide_barcode_in_image(cover_path, pattern, out_path)
            elif method == "DCT":
                (get_dct_jpeg() if jpeg_robust else get_dct()).hide_barcode_in_image(cover_path, pattern, out_path)
            else:
                get_hybrid().hide_barcode_in_image(cover_path, pattern, out_path)
        return None
    except Exception as e:
        return str(e)


@app.route("/api/hide-text", methods=["POST"])
def api_hide_text():
    total_start = time.perf_counter()
    cover = _get_upload_path("cover", (".png", ".bmp", ".jpg", ".jpeg"))
    text = request.form.get("text", "").strip()
    method = request.form.get("method", "LSB")
    if not cover or not text:
        return jsonify({"error": "Cover image and text required"}), 400
    log = []
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf_cover:
        cover_path = tf_cover.name
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf_out:
        out_path = tf_out.name
    try:
        log.append("20% – Saving cover image")
        upload_start = time.perf_counter()
        cover.save(cover_path)
        upload_time = time.perf_counter() - upload_start
        log.append("50% – Hiding text in cover (" + method + ")")
        hide_start = time.perf_counter()
        err = _run_hide(cover_path, out_path, method, text=text)
        hide_time = time.perf_counter() - hide_start
        if err:
            return jsonify({"error": err, "log": log}), 500
        log.append("90% – Writing stego PNG")
        render_start = time.perf_counter()
        with open(out_path, "rb") as r:
            buf = io.BytesIO(r.read())
        buf.seek(0)
        render_time = time.perf_counter() - render_start
        total_time = time.perf_counter() - total_start
        timings = {
            "upload": upload_time,
            "embed_hide": hide_time,
            "preview_render": render_time,
            "total": total_time,
        }
        log.append(f"Timing - Upload: {upload_time:.3f}s")
        log.append(f"Timing - Embed/hide: {hide_time:.3f}s")
        log.append(f"Timing - Render PNG: {render_time:.3f}s")
        log.append(f"Timing - Total: {total_time:.3f}s")
        log.append("100% – Done")
        resp = send_file(buf, mimetype="image/png", as_attachment=True, download_name="stego.png")
        resp.headers["X-Progress-Log"] = json.dumps(log)
        resp.headers["X-Timings-Json"] = json.dumps(timings)
        return resp
    except Exception as e:
        return jsonify({"error": str(e), "log": log}), 500
    finally:
        for p in (cover_path, out_path):
            try:
                os.unlink(p)
            except Exception:
                pass


def _thumbnail_b64(img, max_size=120):
    """Return base64 PNG of a small thumbnail (max side = max_size)."""
    w, h = img.size
    if w > max_size or h > max_size:
        ratio = min(max_size / w, max_size / h)
        new_w, new_h = int(w * ratio), int(h * ratio)
        img = img.resize((new_w, new_h), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _build_hide_barcode_metrics(cover_path, stego_path):
    """Build metrics dict for cover vs stego (dimensions, file sizes, quality, thumbnails)."""
    cover_img = Image.open(cover_path).convert("RGB")
    stego_img = Image.open(stego_path).convert("RGB")
    cw, ch = cover_img.size
    sw, sh = stego_img.size
    cover_pixels = cw * ch
    stego_pixels = sw * sh
    cover_file_kb = os.path.getsize(cover_path) / 1024
    stego_file_kb = os.path.getsize(stego_path) / 1024
    m = QualityMetrics.calculate_all_metrics(cover_path, stego_path)
    hist_c = m.get("Hist_Original") or {}
    hist_s = m.get("Hist_Stego") or {}
    var_c = hist_c.get("variance", 0)
    var_s = hist_s.get("variance", 0)
    chi = m.get("Chi_Square_Suspicion", 0)
    cover_thumb_b64 = _thumbnail_b64(cover_img)
    stego_thumb_b64 = _thumbnail_b64(stego_img)
    return {
        "cover_thumb_b64": cover_thumb_b64,
        "stego_thumb_b64": stego_thumb_b64,
        "PSNR": round(float(m["PSNR"]), 2),
        "SSIM": round(float(m["SSIM"]), 4),
        "BER": round(float(m["BER"]), 4),
        "cover": {
            "width": cw,
            "height": ch,
            "size_str": f"{cw} x {ch}",
            "file_kb": round(cover_file_kb, 2),
            "file_str": f"{cover_file_kb:.2f} KB",
            "pixels": cover_pixels,
            "pixels_str": f"{cover_pixels:,}",
        },
        "stego": {
            "width": sw,
            "height": sh,
            "size_str": f"{sw} x {sh}",
            "file_kb": round(stego_file_kb, 2),
            "file_str": f"{stego_file_kb:.2f} KB",
            "pixels": stego_pixels,
            "pixels_str": f"{stego_pixels:,}",
        },
        "entropy_cover": round(float(m.get("Entropy_Original", 0)), 3),
        "entropy_stego": round(float(m.get("Entropy_Stego", 0)), 3),
        "hist_var_cover": int(var_c),
        "hist_var_stego": int(var_s),
        "chi_square": round(float(chi), 2),
        "diff": {
            "size_kb": round(stego_file_kb - cover_file_kb, 2),
            "dim_w": sw - cw,
            "dim_h": sh - ch,
            "pixels": stego_pixels - cover_pixels,
        },
    }


@app.route("/api/hide-barcode", methods=["POST"])
def api_hide_barcode():
    total_start = time.perf_counter()
    cover = _get_upload_path("cover", (".png", ".bmp", ".jpg", ".jpeg"))
    barcode_f = _get_upload_path("barcode", (".png", ".bmp"))
    method = request.form.get("method", "LSB")
    jpeg_robust = request.form.get("jpeg_robust", "0") == "1"
    if not cover or not barcode_f:
        return jsonify({"error": "Cover and barcode image required"}), 400
    log = []
    cover_path = tempfile.mktemp(suffix=".png")
    barcode_path = tempfile.mktemp(suffix=".png")
    out_path = tempfile.mktemp(suffix=".png")
    try:
        log.append("15% – Saving cover and barcode")
        upload_start = time.perf_counter()
        cover.save(cover_path)
        barcode_f.save(barcode_path)
        upload_time = time.perf_counter() - upload_start
        log.append("40% – Loading barcode pattern, scaling to fill cover")
        hide_start = time.perf_counter()
        err = _run_hide(cover_path, out_path, method, barcode_path=barcode_path, jpeg_robust=jpeg_robust)
        hide_time = time.perf_counter() - hide_start
        if err:
            return jsonify({"error": err, "log": log}), 500
        metrics = None
        # Metrics are expensive on large images; skip to avoid long request stalls.
        out_size = os.path.getsize(out_path)
        cover_w, cover_h = Image.open(cover_path).size
        stego_w, stego_h = Image.open(out_path).size
        pixels_max = max(cover_w * cover_h, stego_w * stego_h)
        metrics_time = 0.0
        if out_size <= 8 * 1024 * 1024 and pixels_max <= 2_000_000:
            log.append("85% – Computing quality metrics")
            metrics_start = time.perf_counter()
            metrics = _build_hide_barcode_metrics(cover_path, out_path)
            metrics_time = time.perf_counter() - metrics_start
        else:
            log.append("85% – Skipping metrics for large output (speed mode)")
        render_start = time.perf_counter()
        log.append("100% – Done")
        # Default: return raw PNG (fast, small vs. base64-in-JSON). Use ?format=json for scripts/tests.
        want_json = request.args.get("format") == "json"
        if want_json:
            with open(out_path, "rb") as r:
                stego_b64 = base64.b64encode(r.read()).decode("utf-8")
            render_time = time.perf_counter() - render_start
            total_time = time.perf_counter() - total_start
            timings = {
                "upload": upload_time,
                "embed_hide": hide_time,
                "metrics": metrics_time if metrics_time > 0 else None,
                "preview_render": render_time,
                "total": total_time,
            }
            return jsonify({"stego_b64": stego_b64, "log": log, "metrics": metrics, "timings": timings})
        with open(out_path, "rb") as r:
            buf = io.BytesIO(r.read())
        buf.seek(0)
        render_time = time.perf_counter() - render_start
        total_time = time.perf_counter() - total_start
        timings = {
            "upload": upload_time,
            "embed_hide": hide_time,
            "metrics": metrics_time if metrics_time > 0 else None,
            "preview_render": render_time,
            "total": total_time,
        }
        log.append(f"Timing - Upload: {upload_time:.3f}s")
        log.append(f"Timing - Embed/hide: {hide_time:.3f}s")
        if metrics_time > 0:
            log.append(f"Timing - Metrics: {metrics_time:.3f}s")
        log.append(f"Timing - Render PNG: {render_time:.3f}s")
        log.append(f"Timing - Total: {total_time:.3f}s")
        resp = send_file(
            buf,
            mimetype="image/png",
            as_attachment=True,
            download_name="stego.png",
        )
        resp.headers["X-Progress-Log"] = json.dumps(log)
        resp.headers["X-Timings-Json"] = json.dumps(timings)
        # Omit base64 thumbnails in headers (size limits); UI can preview from downloaded blob + cover file.
        if metrics:
            slim = {
                k: v
                for k, v in metrics.items()
                if k not in ("cover_thumb_b64", "stego_thumb_b64")
            }
            resp.headers["X-Metrics-Json"] = json.dumps(_to_jsonable(slim))
        return resp
    except Exception as e:
        return jsonify({"error": str(e), "log": log}), 500
    finally:
        for p in (cover_path, barcode_path, out_path):
            try:
                os.unlink(p)
            except Exception:
                pass


@app.route("/api/extract-text", methods=["POST"])
def api_extract_text():
    total_start = time.perf_counter()
    f = _get_upload_path("stego", (".png", ".bmp", ".tiff", ".jpg", ".jpeg"))
    method = request.form.get("method", "LSB")
    if not f:
        return jsonify({"error": "No stego image provided"}), 400
    log = []
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
        path = tf.name
    upload_start = time.perf_counter()
    f.save(path)
    upload_time = time.perf_counter() - upload_start
    try:
        log.append("30% – Loading stego image")
        extract_start = time.perf_counter()
        if method == "LSB":
            text = get_cbs().extract_text_directly(path)
        elif method == "DCT":
            text = get_dct().extract_text_dct(path)
        else:
            text = get_hybrid().extract_text_hybrid(path)
        extract_time = time.perf_counter() - extract_start
        total_time = time.perf_counter() - total_start
        timings = {
            "upload": upload_time,
            "extract": extract_time,
            "total": total_time,
        }
        log.append(f"Timing - Upload: {upload_time:.3f}s")
        log.append(f"Timing - Extract: {extract_time:.3f}s")
        log.append(f"Timing - Total: {total_time:.3f}s")
        log.append("100% – Done")
        return jsonify({"text": text, "log": log, "progress": 100, "timings": timings})
    except Exception as e:
        return jsonify({"error": str(e), "log": log}), 500
    finally:
        try:
            os.unlink(path)
        except Exception:
            pass


def _decode_barcode_pattern(cbs, pattern, use_hybrid_decryption=True):
    """
    Decode barcode pattern to text. If the pattern was scaled when hiding
    (expand-to-fill-cover), the extracted pattern is larger than the logical
    CBS pattern; try downsampling by 2, 3, ... and decode until valid.
    """
    last_error = None
    try:
        return cbs.decode(pattern, use_hybrid_decryption=use_hybrid_decryption)
    except ValueError as e:
        last_error = e
    msg = str(last_error) if last_error else ""
    if "Invalid barcode format" not in msg and "Failed to decode text from bits" not in msg:
        raise last_error
    h, w = pattern.shape[0], pattern.shape[1]

    def _safe_decode(candidate):
        return cbs.decode(candidate, use_hybrid_decryption=use_hybrid_decryption)

    # For scaled patterns, decode may fail if sample alignment is slightly shifted.
    # Try multiple offsets and a majority-pool fallback for each candidate scale.
    def _majority_downsample(pat, k):
        hh = (pat.shape[0] // k) * k
        ww = (pat.shape[1] // k) * k
        if hh < 3 or ww < 3:
            return None
        cropped = pat[:hh, :ww]
        blocks = cropped.reshape(hh // k, k, ww // k, k)
        med = np.median(blocks, axis=(1, 3))
        return np.rint(med).astype(np.uint8)
    max_k = min(h, w) // 3
    if max_k < 2:
        raise last_error
    gcd_hw = int(np.gcd(h, w))
    candidate_scales = []
    for k in range(2, min(gcd_hw, max_k) + 1):
        if h % k == 0 and w % k == 0:
            candidate_scales.append(k)
    # Fall back to small scales if no exact common divisors found.
    if not candidate_scales:
        candidate_scales = list(range(2, min(8, max_k) + 1))
    # Larger scales are more likely for expand-to-fill flow; try those first.
    candidate_scales.sort(reverse=True)

    for k in candidate_scales:
        offsets = [0]
        if k > 2:
            offsets.extend([k // 2, k - 1])
        for oy in offsets:
            for ox in offsets:
                small = pattern[oy::k, ox::k].copy()
                if small.shape[0] < 3 or small.shape[1] < 3:
                    continue
                try:
                    return _safe_decode(small)
                except ValueError as e:
                    last_error = e
        pooled = _majority_downsample(pattern, k)
        if pooled is not None and pooled.shape[0] >= 3 and pooled.shape[1] >= 3:
            try:
                return _safe_decode(pooled)
            except ValueError as e:
                last_error = e
                continue
    raise last_error


@app.route("/api/extract-barcode", methods=["POST"])
def api_extract_barcode():
    total_start = time.perf_counter()
    f = _get_upload_path("stego", (".png", ".bmp", ".tiff", ".jpg", ".jpeg"))
    method = request.form.get("method", "LSB")
    if not f:
        return jsonify({"error": "No stego image provided"}), 400
    log = []
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
        path = tf.name
    upload_start = time.perf_counter()
    f.save(path)
    upload_time = time.perf_counter() - upload_start
    try:
        log.append("25% – Loading stego image")
        extract_start = time.perf_counter()
        if method == "LSB":
            pattern = get_barcode_stego().extract_barcode_from_image(path)
        elif method == "DCT":
            pattern = get_dct().extract_barcode_from_image(path)
        else:
            pattern = get_hybrid().extract_barcode_from_image(path)
        extract_time = time.perf_counter() - extract_start

        decode_start = time.perf_counter()
        text = _decode_barcode_pattern(get_cbs(), pattern, use_hybrid_decryption=True)
        decode_time = time.perf_counter() - decode_start

        log.append("70% – Decoding barcode")
        # Huge base64 previews break mobile browsers / JSON parse; omit when pattern is large.
        max_preview_pixels = 1_200_000
        preview_start = time.perf_counter()
        if pattern.size <= max_preview_pixels:
            b64 = base64.b64encode(_barcode_pattern_to_bytes(pattern).read()).decode("utf-8")
        else:
            b64 = None
        preview_time = time.perf_counter() - preview_start
        is_image = text.startswith("[IMAGE:") and "[HYBRID_ENCRYPTED" not in text
        total_time = time.perf_counter() - total_start
        timings = {
            "upload": upload_time,
            "extract_barcode": extract_time,
            "decode_payload": decode_time,
            "preview_render": preview_time,
            "total": total_time,
        }
        log.append(f"Timing - Upload: {upload_time:.3f}s")
        log.append(f"Timing - Extract barcode: {extract_time:.3f}s")
        log.append(f"Timing - Decode payload: {decode_time:.3f}s")
        if b64 is not None:
            log.append(f"Timing - Preview render: {preview_time:.3f}s")
        log.append(f"Timing - Total: {total_time:.3f}s")
        log.append("100% – Done")
        return jsonify(
            {
                "text": text,
                "barcode_b64": b64,
                "barcode_preview_omitted": b64 is None,
                "is_image": is_image,
                "log": log,
                "progress": 100,
                "timings": timings,
            }
        )
    except Exception as e:
        return jsonify({"error": str(e), "log": log}), 500
    finally:
        try:
            os.unlink(path)
        except Exception:
            pass


@app.route("/api/denoise", methods=["POST"])
def api_denoise():
    total_start = time.perf_counter()
    f = _get_upload_path("image", (".png", ".bmp", ".jpg", ".jpeg"))
    method = request.form.get("method", "median")
    size = int(request.form.get("median_size", "3"))
    sigma = float(request.form.get("sigma", "1.0"))
    if not f:
        return jsonify({"error": "No image provided"}), 400
    log = []
    try:
        log.append("20% – Loading image")
        load_start = time.perf_counter()
        img = Image.open(f.stream).convert("RGB")
        arr = np.array(img, dtype=np.float32)
        load_time = time.perf_counter() - load_start
        log.append("50% – Applying " + method + " filter")
        filter_start = time.perf_counter()
        if method == "median":
            arr = apply_median_filter(arr, size)
        else:
            arr = apply_gaussian_filter(arr, sigma)
        filter_time = time.perf_counter() - filter_start
        arr = np.clip(arr, 0, 255).astype(np.uint8)
        log.append("85% – Writing PNG")
        render_start = time.perf_counter()
        out = io.BytesIO()
        Image.fromarray(arr).save(out, "PNG")
        out.seek(0)
        render_time = time.perf_counter() - render_start
        total_time = time.perf_counter() - total_start
        timings = {
            "load": load_time,
            "filter": filter_time,
            "preview_render": render_time,
            "total": total_time,
        }
        log.append(f"Timing - Load: {load_time:.3f}s")
        log.append(f"Timing - Filter: {filter_time:.3f}s")
        log.append(f"Timing - Render PNG: {render_time:.3f}s")
        log.append(f"Timing - Total: {total_time:.3f}s")
        log.append("100% – Done")
        resp = send_file(out, mimetype="image/png", as_attachment=True, download_name="denoised.png")
        resp.headers["X-Progress-Log"] = json.dumps(log)
        resp.headers["X-Timings-Json"] = json.dumps(timings)
        return resp
    except Exception as e:
        return jsonify({"error": str(e), "log": log}), 500


@app.route("/api/metrics", methods=["POST"])
def api_metrics():
    total_start = time.perf_counter()
    orig = _get_upload_path("original", (".png", ".bmp", ".jpg", ".jpeg"))
    stego = _get_upload_path("stego", (".png", ".bmp", ".jpg", ".jpeg"))
    if not orig or not stego:
        return jsonify({"error": "Original and stego images required"}), 400
    log = []
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf_orig:
        op = tf_orig.name
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf_stego:
        sp = tf_stego.name
    save_start = time.perf_counter()
    orig.save(op)
    stego.save(sp)
    save_time = time.perf_counter() - save_start
    try:
        log.append("30% – Loading images")
        log.append("70% – Computing metrics")
        metrics_start = time.perf_counter()
        m = QualityMetrics.calculate_all_metrics(op, sp)
        metrics_time = time.perf_counter() - metrics_start
        total_time = time.perf_counter() - total_start
        timings = {
            "upload": save_time,
            "metrics": metrics_time,
            "total": total_time,
        }
        log.append(f"Timing - Upload: {save_time:.3f}s")
        log.append(f"Timing - Metrics: {metrics_time:.3f}s")
        log.append(f"Timing - Total: {total_time:.3f}s")
        log.append("100% – Done")
        out = _to_jsonable(m)
        out["log"] = log
        out["progress"] = 100
        out["timings"] = timings
        return jsonify(out)
    except Exception as e:
        return jsonify({"error": str(e), "log": log}), 500
    finally:
        for p in (op, sp):
            try:
                os.unlink(p)
            except Exception:
                pass


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    app.run(debug=True, port=5000)
