"""
Generate PNG figures + metrics JSON for LaTeX Chapter 5 (System Testing).
Run from repo root: python scripts/generate_chapter5_thesis_figures.py

Outputs (default): stego_project/Figures/
  - test_system.png
  - test_integration.png
  - comparison.png
  - chapter5_metrics.json  (PSNR/SSIM/BER from real hide-barcode runs)
"""
from __future__ import annotations

import base64
import io
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib import gridspec
import numpy as np
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIGURES = PROJECT_ROOT / "Figures"
sys.path.insert(0, str(PROJECT_ROOT))

from web.app import app  # noqa: E402
from metrics.quality import QualityMetrics  # noqa: E402


def make_cover_png(path: Path, w: int = 320, h: int = 320, color=(88, 110, 132)) -> None:
    Image.new("RGB", (w, h), color).save(path, "PNG")


def make_barcode(client, text: str) -> bytes:
    r = client.post("/api/encode", data={"text": text, "use_hybrid": "0"})
    if r.status_code != 200:
        raise RuntimeError(f"encode failed {r.status_code}")
    return r.data


def hide_barcode_stego(client, cover_path: Path, barcode_bytes: bytes, method: str) -> bytes:
    with open(cover_path, "rb") as f:
        cover_data = f.read()
    r = client.post(
        f"/api/hide-barcode?format=json",
        data={
            "method": method,
            "jpeg_robust": "0",
            "cover": (io.BytesIO(cover_data), "cover.png"),
            "barcode": (io.BytesIO(barcode_bytes), "barcode.png"),
        },
        content_type="multipart/form-data",
    )
    j = r.get_json(silent=True) or {}
    if r.status_code != 200:
        raise RuntimeError(j.get("error", str(r.status_code)))
    return base64.b64decode(j["stego_b64"])


def pil_from_bytes(b: bytes) -> Image.Image:
    return Image.open(io.BytesIO(b)).convert("RGB")


def show_rgb(ax, img: Image.Image, title: str) -> None:
    ax.imshow(np.asarray(img))
    ax.set_title(title, fontsize=11)
    ax.axis("off")


def main() -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    cover_p = FIGURES / "_gen_cover.png"
    make_cover_png(cover_p)

    client = app.test_client()
    payload = "Thesis evaluation — barcode stego round-trip"
    barcode_b = make_barcode(client, payload)

    barcode_img = pil_from_bytes(barcode_b)
    cover_img = Image.open(cover_p).convert("RGB")

    stegos: dict[str, Image.Image] = {}
    metrics_rows: dict[str, dict] = {}
    tmp_stego = FIGURES / "_tmp_stego.png"
    for method in ("LSB", "DCT", "Hybrid"):
        stego_b = hide_barcode_stego(client, cover_p, barcode_b, method)
        tmp_stego.write_bytes(stego_b)
        stegos[method] = pil_from_bytes(stego_b)
        m = QualityMetrics.calculate_all_metrics(str(cover_p), str(tmp_stego))
        metrics_rows[method] = {
            "PSNR": round(float(m["PSNR"]), 2),
            "SSIM": round(float(m["SSIM"]), 4),
            "BER": round(float(m["BER"]), 4),
        }

    (FIGURES / "chapter5_metrics.json").write_text(
        json.dumps(metrics_rows, indent=2), encoding="utf-8"
    )

    # --- Figure: test_system (encode → hide pipeline)
    fig, axes = plt.subplots(1, 3, figsize=(10.5, 3.4))
    show_rgb(axes[0], barcode_img, "(1) Encoded barcode")
    show_rgb(axes[1], cover_img, "(2) Cover image")
    show_rgb(axes[2], stegos["LSB"], "(3) Stego (LSB hide-barcode)")
    fig.suptitle("System testing: end-to-end encoding and embedding", fontsize=13, y=1.02)
    plt.tight_layout()
    fig.savefig(FIGURES / "test_system.png", dpi=200, bbox_inches="tight")
    plt.close()

    # --- Figure: deployment / integration
    fig, ax = plt.subplots(figsize=(9, 3.2))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 3)
    ax.axis("off")
    boxes = [
        (0.3, 1.0, 1.6, 1.0, "Client\n(browser)"),
        (2.5, 1.0, 1.6, 1.0, "Nginx\n:443 TLS"),
        (4.7, 1.0, 1.6, 1.0, "Gunicorn\n:5000"),
        (6.9, 1.0, 1.6, 1.0, "Flask app\n(stego)"),
    ]
    for x, y, w, h, label in boxes:
        r = mpatches.FancyBboxPatch(
            (x, y), w, h, boxstyle="round,pad=0.05", facecolor="#e8eef5", edgecolor="#334155"
        )
        ax.add_patch(r)
        ax.text(x + w / 2, y + h / 2, label, ha="center", va="center", fontsize=10)
    for i, x in enumerate([1.9, 4.1, 6.3]):
        ax.annotate(
            "",
            xy=(x + 0.55, 1.5),
            xytext=(x + 0.05, 1.5),
            arrowprops=dict(arrowstyle="->", lw=1.5, color="#1e3a5f"),
        )
    ax.text(5, 2.45, "Integrated deployment (stegax.design stack)", ha="center", fontsize=13)
    fig.savefig(FIGURES / "test_integration.png", dpi=200, bbox_inches="tight")
    plt.close()

    # --- Figure: comparison (three stego + per-metric bars)
    fig = plt.figure(figsize=(10, 6))
    gs = gridspec.GridSpec(2, 3, height_ratios=[1.2, 0.85], hspace=0.4, wspace=0.2)
    methods = ["LSB", "DCT", "Hybrid"]
    for i, m in enumerate(methods):
        ax = fig.add_subplot(gs[0, i])
        show_rgb(ax, stegos[m], f"Stego — {m}")
    psnrs = [metrics_rows[m]["PSNR"] for m in methods]
    ssims = [metrics_rows[m]["SSIM"] for m in methods]
    bers = [metrics_rows[m]["BER"] for m in methods]
    x = np.arange(len(methods))
    for j, (vals, ylab, title, c) in enumerate(
        [
            (psnrs, "PSNR (dB)", "PSNR", "#3b82f6"),
            (ssims, "SSIM", "SSIM", "#22c55e"),
            (bers, "BER (%)", "BER", "#f97316"),
        ]
    ):
        axb = fig.add_subplot(gs[1, j])
        axb.bar(x, vals, color=c, width=0.55)
        axb.set_xticks(x)
        axb.set_xticklabels(methods)
        axb.set_ylabel(ylab)
        axb.set_title(title, fontsize=10)
    fig.suptitle("A/B comparison: same cover & barcode, different embedding methods", fontsize=12)
    fig.savefig(FIGURES / "comparison.png", dpi=200, bbox_inches="tight")
    plt.close()

    if tmp_stego.exists():
        tmp_stego.unlink()

    print("Wrote:", FIGURES / "test_system.png")
    print("Wrote:", FIGURES / "test_integration.png")
    print("Wrote:", FIGURES / "comparison.png")
    print("Wrote:", FIGURES / "chapter5_metrics.json")
    print("\nLaTeX table rows (paste into tabular):")
    for m in methods:
        r = metrics_rows[m]
        print(f"{m} & {r['PSNR']} & {r['SSIM']} & {r['BER']} \\\\")


if __name__ == "__main__":
    main()
