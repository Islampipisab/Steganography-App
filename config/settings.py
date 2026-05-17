"""
Application configuration and constants.
Centralizes magic headers, limits, and default values.
"""

# PIL image size limit (pixels) - allow large images
MAX_IMAGE_PIXELS = 500_000_000

# Default barcode scale factor (pixels per pattern cell)
DEFAULT_BARCODE_SCALE = 10

# RSA key file names (relative to cwd unless overridden)
DEFAULT_PRIVATE_KEY_PATH = "private_key.pem"
DEFAULT_PUBLIC_KEY_PATH = "public_key.pem"

# Magic headers (bytes) - used by steganography and barcode formats
MAGIC_HEADER_BCSTEGO = b'BCSTEGO\x01'
MAGIC_HEADER_DCTSTEGO = b'DCTSTEGO\x01\x02\x03'
MAGIC_HEADER_DCTBAR = b'DCTBAR\x01'
MAGIC_HEADER_HYBRID = b'HYBRID\x01\x02\x03'
MAGIC_HEADER_HYBAR = b'HYBAR\x01\x02'
MAGIC_HEADER_CBS = b'CBS\x01'
MAGIC_HEADER_PASSWORD = b'PASS' + b'\x01\x02\x03'

# DCT parameters
DCT_BLOCK_SIZE = 8
DCT_QUANTIZATION_NORMAL = 10.0
DCT_QUANTIZATION_JPEG_ROBUST = 150.0
DCT_JPEG_ROBUST_QUANT_FACTORS = [150.0, 120.0, 100.0, 80.0, 60.0]

# Hybrid LSB/DCT ratio (0.5 = 50% LSB, 50% DCT)
HYBRID_LSB_RATIO = 0.5

# Custom barcode error correction
CBS_BLOCK_SIZE = 8

# Encryption (block encryption for large images) - encrypt first N% of image data
BLOCK_ENCRYPTION_PERCENTAGE = 20
