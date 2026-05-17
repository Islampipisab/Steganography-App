# Steganography System

Modular barcode and image steganography application with LSB, DCT, and Hybrid methods.

## Setup

```bash
cd stego_project
pip install -r requirements.txt
```

## Run

**Desktop (tkinter):**
```bash
python main.py
```

**Web app:**
```bash
python web/app.py
```
Then open http://localhost:5000 in your browser. The app allows uploads up to 200 MB. If you see "Request Entity Too Large" behind a reverse proxy (e.g. nginx), increase its body limit (e.g. `client_max_body_size 200M;`).

## Project structure

- `config/` – settings and constants
- `core/` – LSB, DCT, Hybrid steganography
- `crypto/` – Hybrid (RSA+AES) and password encryption
- `barcode/` – custom barcode encode/decode
- `metrics/` – image quality (PSNR, SSIM, BER, etc.)
- `processing/` – denoising (median, Gaussian filters)
- `ui/` – tkinter GUI
- `web/` – Flask app, templates, static (CSS/JS)
- `tests/` – tests

## Deploy to cloud

To upload and run on a server (e.g. 46.101.244.129), see **[DEPLOY.md](DEPLOY.md)**. Use the `deploy.ps1` script or SCP to upload, then run with Gunicorn on the server.

## Tests

From `stego_project`:

```bash
pytest tests/ -v
```
