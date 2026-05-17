"""
DCT-based steganography (Discrete Cosine Transform).
Robust to compression; supports JPEG-robust mode.
"""
import struct
import numpy as np
from PIL import Image
from scipy.fftpack import dct, idct

from config.settings import (
    MAGIC_HEADER_DCTSTEGO,
    MAGIC_HEADER_DCTBAR,
    DCT_BLOCK_SIZE,
    DCT_QUANTIZATION_NORMAL,
    DCT_QUANTIZATION_JPEG_ROBUST,
    DCT_JPEG_ROBUST_QUANT_FACTORS,
)


class DCTSteganography:
    """DCT-based Steganography using Discrete Cosine Transform - Robust Implementation."""

    def __init__(self, jpeg_robust_mode=False):
        self.magic_header = MAGIC_HEADER_DCTSTEGO
        self.block_size = DCT_BLOCK_SIZE
        self.jpeg_robust_mode = jpeg_robust_mode

        if jpeg_robust_mode:
            self.quantization_factor = DCT_QUANTIZATION_JPEG_ROBUST
            self.embed_positions = [(0, 1), (1, 0), (1, 1)]
        else:
            self.quantization_factor = DCT_QUANTIZATION_NORMAL
            self.embed_positions = [
                (1, 1), (0, 1), (1, 0), (2, 0), (0, 2), (2, 1), (1, 2), (2, 2)
            ]

    def _text_to_bits(self, text):
        text_bytes = text.encode("utf-8")
        data_to_hide = self.magic_header + struct.pack(">I", len(text_bytes)) + text_bytes
        bits = []
        for byte in data_to_hide:
            for i in range(8):
                bits.append((byte >> (7 - i)) & 1)
        return bits

    def _bits_to_text(self, bits):
        bytes_data = []
        for i in range(0, len(bits), 8):
            if i + 8 <= len(bits):
                byte_val = 0
                for j in range(8):
                    byte_val |= (bits[i + j] << (7 - j))
                bytes_data.append(byte_val)
        bytes_data = bytes(bytes_data)
        if not bytes_data.startswith(self.magic_header):
            raise ValueError("Invalid DCT stego format or magic header not found.")
        header_len = len(self.magic_header)
        if len(bytes_data) < header_len + 4:
            raise ValueError("Incomplete header: cannot extract text length.")
        length = struct.unpack(">I", bytes_data[header_len : header_len + 4])[0]
        text_start_index = header_len + 4
        text_bytes = bytes_data[text_start_index : text_start_index + length]
        if len(text_bytes) != length:
            raise ValueError("Incomplete text data extracted.")
        try:
            return text_bytes.decode("utf-8")
        except UnicodeDecodeError:
            return text_bytes.decode("utf-8", errors="replace")

    def _embed_bits_in_dct(self, dct_block, bits, bit_index):
        embedded_count = 0
        for pos in self.embed_positions:
            if bit_index >= len(bits):
                break
            i, j = pos
            coeff = dct_block[i, j]
            quantized = round(coeff / self.quantization_factor)
            if bits[bit_index] == 1:
                quantized = quantized | 1
            else:
                quantized = quantized & ~1
            dct_block[i, j] = quantized * self.quantization_factor
            bit_index += 1
            embedded_count += 1
        return bit_index, embedded_count

    def _extract_bits_from_dct(self, dct_block, num_bits):
        bits = []
        for i, pos in enumerate(self.embed_positions):
            if i >= num_bits:
                break
            x, y = pos
            coeff = dct_block[x, y]
            quantized = round(coeff / self.quantization_factor)
            bit = quantized & 1
            bits.append(bit)
        return bits

    def hide_text_dct(self, cover_image_path, text, output_path):
        cover_img = Image.open(cover_image_path).convert("RGB")
        cover_array = np.array(cover_img, dtype=np.float32)
        height, width, channels = cover_array.shape
        bits_to_hide = self._text_to_bits(text)
        blocks_per_row = width // self.block_size
        blocks_per_col = height // self.block_size
        bits_per_block = len(self.embed_positions)
        max_capacity = blocks_per_row * blocks_per_col * bits_per_block * channels
        if len(bits_to_hide) > max_capacity:
            total_blocks = blocks_per_row * blocks_per_col * channels
            needed_blocks = (len(bits_to_hide) + bits_per_block - 1) // bits_per_block
            raise ValueError(
                "Barcode too large: If the barcode data exceeds the DCT coefficient capacity, it can't be fully embedded.\n\n"
                f"Details:\n  - Cover image size: {width}x{height} pixels\n"
                f"  - Available DCT blocks: {total_blocks} blocks\n"
                f"  - Required DCT blocks: {needed_blocks} blocks\n"
                f"  - Max capacity: {max_capacity} bits\n  - Required: {len(bits_to_hide)} bits\n"
                f"  - Shortage: {len(bits_to_hide) - max_capacity} bits\n\n"
                "Solution: Use a larger cover image or reduce the barcode data size."
            )
        stego_array = cover_array.copy()
        bit_index = 0
        for c in range(channels):
            channel = stego_array[:, :, c]
            for block_y in range(0, height - self.block_size + 1, self.block_size):
                for block_x in range(0, width - self.block_size + 1, self.block_size):
                    if bit_index >= len(bits_to_hide):
                        break
                    block = channel[
                        block_y : block_y + self.block_size,
                        block_x : block_x + self.block_size,
                    ]
                    dct_block = dct(dct(block, axis=0, norm="ortho"), axis=1, norm="ortho")
                    if bit_index < len(bits_to_hide):
                        bit_index, _ = self._embed_bits_in_dct(
                            dct_block, bits_to_hide, bit_index
                        )
                    idct_block = idct(
                        idct(dct_block, axis=0, norm="ortho"), axis=1, norm="ortho"
                    )
                    stego_array[
                        block_y : block_y + self.block_size,
                        block_x : block_x + self.block_size,
                        c,
                    ] = idct_block
                if bit_index >= len(bits_to_hide):
                    break
            if bit_index >= len(bits_to_hide):
                break
        stego_array = np.clip(stego_array, 0, 255)
        stego_array = np.round(stego_array).astype(np.uint8)
        stego_img = Image.fromarray(stego_array, "RGB")
        if not output_path.lower().endswith(".png"):
            output_path = output_path.rsplit(".", 1)[0] + ".png"
        stego_img.save(output_path, "PNG", compress_level=0)

    def hide_barcode_in_image(self, cover_image_path, barcode_pattern, output_path):
        cover_img = Image.open(cover_image_path).convert("RGB")
        cover_array = np.array(cover_img, dtype=np.float32)
        height, width, channels = cover_array.shape
        flat_pat = np.asarray(barcode_pattern, dtype=np.uint8).reshape(-1)
        pat_bits = np.empty(flat_pat.size * 2, dtype=np.uint8)
        pat_bits[0::2] = (flat_pat >> 1) & 1
        pat_bits[1::2] = flat_pat & 1
        barcode_height, barcode_width = barcode_pattern.shape
        header_bits = []
        magic = MAGIC_HEADER_DCTBAR
        for byte in magic:
            for i in range(7, -1, -1):
                header_bits.append((byte >> i) & 1)
        for dim in [barcode_height, barcode_width]:
            for i in range(15, -1, -1):
                header_bits.append((dim >> i) & 1)
        scale = 10
        for i in range(7, -1, -1):
            header_bits.append((scale >> i) & 1)
        all_bits = np.concatenate([np.asarray(header_bits, dtype=np.uint8), pat_bits])
        blocks_per_row = width // self.block_size
        blocks_per_col = height // self.block_size
        bits_per_block = len(self.embed_positions)
        max_capacity = blocks_per_row * blocks_per_col * bits_per_block * channels
        if len(all_bits) > max_capacity:
            print("WARNING: Cover image too small for DCT barcode! Resizing...")
            needed_blocks = (len(all_bits) + bits_per_block * channels - 1) // (
                bits_per_block * channels
            )
            min_dim = int(np.sqrt(needed_blocks)) * self.block_size
            target_dim = int(min_dim * 1.2)
            print(f"Resizing from {width}x{height} to {target_dim}x{target_dim}")
            cover_img = cover_img.resize((target_dim, target_dim), Image.LANCZOS)
            cover_array = np.array(cover_img, dtype=np.float32)
            height, width, channels = cover_array.shape
            blocks_per_row = width // self.block_size
            blocks_per_col = height // self.block_size
            max_capacity = blocks_per_row * blocks_per_col * bits_per_block * channels
            if len(all_bits) > max_capacity:
                raise ValueError(
                    f"Resize failed. Need {len(all_bits)} bits, capacity {max_capacity}."
                )
        stego_array = cover_array.copy()
        bit_index = 0
        for c in range(channels):
            channel = stego_array[:, :, c]
            for block_y in range(0, height - self.block_size + 1, self.block_size):
                for block_x in range(0, width - self.block_size + 1, self.block_size):
                    if bit_index >= len(all_bits):
                        break
                    block = channel[
                        block_y : block_y + self.block_size,
                        block_x : block_x + self.block_size,
                    ]
                    dct_block = dct(dct(block, axis=0, norm="ortho"), axis=1, norm="ortho")
                    if bit_index < len(all_bits):
                        bit_index, _ = self._embed_bits_in_dct(
                            dct_block, all_bits, bit_index
                        )
                    idct_block = idct(
                        idct(dct_block, axis=0, norm="ortho"), axis=1, norm="ortho"
                    )
                    stego_array[
                        block_y : block_y + self.block_size,
                        block_x : block_x + self.block_size,
                        c,
                    ] = idct_block
                if bit_index >= len(all_bits):
                    break
            if bit_index >= len(all_bits):
                break
        stego_array = np.clip(stego_array, 0, 255)
        stego_array = np.round(stego_array).astype(np.uint8)
        stego_img = Image.fromarray(stego_array, "RGB")
        if not output_path.lower().endswith(".png"):
            output_path = output_path.rsplit(".", 1)[0] + ".png"
        stego_img.save(output_path, "PNG", compress_level=6)

    def _extract_text_dct_internal(self, stego_image_path, jpeg_robust=False):
        old_mode = self.jpeg_robust_mode
        old_factor = self.quantization_factor
        old_positions = self.embed_positions
        if jpeg_robust:
            self.jpeg_robust_mode = True
            self.quantization_factor = 80.0
            self.embed_positions = [(0, 1), (1, 0), (1, 1)]
        else:
            self.jpeg_robust_mode = False
            self.quantization_factor = 10.0
            self.embed_positions = [
                (1, 1), (0, 1), (1, 0), (2, 0), (0, 2), (2, 1), (1, 2), (2, 2)
            ]
        try:
            stego_img = Image.open(stego_image_path).convert("RGB")
            stego_array = np.array(stego_img, dtype=np.float32)
            height, width, channels = stego_array.shape
            extracted_bits = []
            magic_header_bits = len(self.magic_header) * 8
            min_bits_needed = magic_header_bits + 32
            for c in range(channels):
                channel = stego_array[:, :, c]
                for block_y in range(0, height - self.block_size + 1, self.block_size):
                    for block_x in range(0, width - self.block_size + 1, self.block_size):
                        block = channel[
                            block_y : block_y + self.block_size,
                            block_x : block_x + self.block_size,
                        ]
                        dct_block = dct(
                            dct(block, axis=0, norm="ortho"), axis=1, norm="ortho"
                        )
                        bits = self._extract_bits_from_dct(
                            dct_block, len(self.embed_positions)
                        )
                        extracted_bits.extend(bits)
                        if (
                            len(extracted_bits) >= min_bits_needed
                            and len(extracted_bits) % 50 == 0
                        ):
                            try:
                                return self._bits_to_text(extracted_bits)
                            except ValueError:
                                pass
        finally:
            self.jpeg_robust_mode = old_mode
            self.quantization_factor = old_factor
            self.embed_positions = old_positions
        raise ValueError("Could not extract text - magic header not found")

    def extract_text_dct(self, stego_image_path, try_jpeg_robust=True):
        img_format = Image.open(stego_image_path).format
        is_jpeg = img_format and img_format.upper() in ["JPEG", "JPG"]
        if not is_jpeg and img_format and img_format.upper() not in ["PNG", "BMP", "TIFF"]:
            raise ValueError(
                f"DCT requires lossless format (PNG/BMP/TIFF) or JPEG. Image is '{img_format}'."
            )
        if is_jpeg or try_jpeg_robust:
            try:
                return self._extract_text_dct_internal(
                    stego_image_path, jpeg_robust=True
                )
            except ValueError:
                pass
        return self._extract_text_dct_internal(stego_image_path, jpeg_robust=False)

    def extract_barcode_from_image(self, stego_image_path, try_jpeg_robust=True):
        img_format = Image.open(stego_image_path).format
        is_jpeg = img_format and img_format.upper() in ["JPEG", "JPG"]
        if not is_jpeg and img_format and img_format.upper() not in ["PNG", "BMP", "TIFF"]:
            raise ValueError(
                f"DCT requires lossless format (PNG/BMP/TIFF) or JPEG. Image is '{img_format}'."
            )
        if not is_jpeg:
            try:
                return self._extract_barcode_internal(
                    stego_image_path, jpeg_robust=False
                )
            except (ValueError, Exception) as e:
                if try_jpeg_robust:
                    try:
                        return self._extract_barcode_internal(
                            stego_image_path, jpeg_robust=True
                        )
                    except (ValueError, Exception):
                        raise e
                raise e
        try:
            return self._extract_barcode_internal(
                stego_image_path, jpeg_robust=True
            )
        except (ValueError, Exception):
            if try_jpeg_robust:
                return self._extract_barcode_internal(
                    stego_image_path, jpeg_robust=False
                )
            raise

    def _extract_barcode_internal(self, stego_image_path, jpeg_robust=False):
        old_mode = self.jpeg_robust_mode
        old_quant = self.quantization_factor
        old_positions = self.embed_positions
        try:
            if jpeg_robust:
                self.jpeg_robust_mode = True
                self.embed_positions = [(0, 1), (1, 0), (1, 1)]
                for quant_factor in DCT_JPEG_ROBUST_QUANT_FACTORS:
                    try:
                        self.quantization_factor = quant_factor
                        return self._try_extract_barcode(stego_image_path)
                    except (ValueError, Exception):
                        continue
                raise ValueError(
                    "Could not extract DCT barcode. Image may be too heavily compressed or not contain DCT barcode."
                )
            self.jpeg_robust_mode = False
            self.quantization_factor = 10.0
            self.embed_positions = [
                (1, 1), (0, 1), (1, 0), (2, 0), (0, 2), (2, 1), (1, 2), (2, 2)
            ]
            return self._try_extract_barcode(stego_image_path)
        finally:
            self.jpeg_robust_mode = old_mode
            self.quantization_factor = old_quant
            self.embed_positions = old_positions

    def _try_extract_barcode(self, stego_image_path):
        stego_img = Image.open(stego_image_path).convert("RGB")
        stego_array = np.array(stego_img, dtype=np.float32)
        height, width, channels = stego_array.shape
        extracted_bits = []
        for c in range(channels):
            channel = stego_array[:, :, c]
            for block_y in range(0, height - self.block_size + 1, self.block_size):
                for block_x in range(0, width - self.block_size + 1, self.block_size):
                    block = channel[
                        block_y : block_y + self.block_size,
                        block_x : block_x + self.block_size,
                    ]
                    dct_block = dct(
                        dct(block, axis=0, norm="ortho"), axis=1, norm="ortho"
                    )
                    bits = self._extract_bits_from_dct(
                        dct_block, len(self.embed_positions)
                    )
                    extracted_bits.extend(bits)
        magic = MAGIC_HEADER_DCTBAR
        magic_bits = []
        for byte in magic:
            for i in range(7, -1, -1):
                magic_bits.append((byte >> i) & 1)
        search_limit = min(len(extracted_bits), 10000)

        def check_header(idx, max_errors=2):
            if idx + len(magic_bits) > len(extracted_bits):
                return False
            errors = 0
            for k in range(len(magic_bits)):
                if extracted_bits[idx + k] != magic_bits[k]:
                    errors += 1
                    if errors > max_errors:
                        return False
            return True

        start_index = -1
        # Lossless PNG/BMP: require an exact DCTBAR header. Fuzzy matching (used for
        # JPEG-robust) false-positives on LSB/Hybrid stego images and yields decoded garbage.
        max_tolerance = 5 if self.jpeg_robust_mode else 0
        for tolerance in range(max_tolerance + 1):
            for i in range(0, search_limit, 1):
                if check_header(i, max_errors=tolerance):
                    start_index = i
                    break
            if start_index != -1:
                break

        if start_index == -1:
            raise ValueError(
                "No DCT barcode header found. Image might be cropped, compressed, or not contain a DCT barcode.\n\n"
                "Try:\n1. Ensure you used JPEG-Robust mode when hiding\n"
                "2. Check if the image was heavily compressed\n"
                "3. Try extracting with a different method (LSB)"
            )

        current_pos = start_index + len(magic_bits)

        def extract_int(pos, bits):
            val = 0
            for k in range(bits):
                val |= extracted_bits[pos + k] << (bits - 1 - k)
            return val

        barcode_height = extract_int(current_pos, 16)
        current_pos += 16
        barcode_width = extract_int(current_pos, 16)
        current_pos += 16
        scale = extract_int(current_pos, 8)
        current_pos += 8
        pattern_size = barcode_height * barcode_width * 2
        if current_pos + pattern_size > len(extracted_bits):
            raise ValueError("Incomplete barcode data in DCT coefficients.")
        pattern_bits = extracted_bits[current_pos : current_pos + pattern_size]
        barcode_pattern = np.zeros((barcode_height, barcode_width), dtype=np.uint8)
        bit_index = 0
        for y in range(barcode_height):
            for x in range(barcode_width):
                if bit_index + 1 < len(pattern_bits):
                    msb = pattern_bits[bit_index]
                    lsb = pattern_bits[bit_index + 1]
                    barcode_pattern[y, x] = (msb << 1) | lsb
                    bit_index += 2
        self._last_extracted_scale = scale
        return barcode_pattern

    def get_last_extracted_scale(self):
        return getattr(self, "_last_extracted_scale", 10)
