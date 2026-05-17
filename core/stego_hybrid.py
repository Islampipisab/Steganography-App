"""
Hybrid steganography: LSB (Red channel) + DCT (Green, Blue).
Combines robustness of both methods.
"""
import struct
import numpy as np
from PIL import Image
from scipy.fftpack import dct, idct

from config.settings import MAGIC_HEADER_HYBRID, MAGIC_HEADER_HYBAR, HYBRID_LSB_RATIO
from .stego_lsb import BarcodeSteganography
from .stego_dct import DCTSteganography


class HybridSteganography:
    """Hybrid Steganography combining LSB and DCT methods for enhanced robustness."""

    def __init__(self):
        self.magic_header = MAGIC_HEADER_HYBRID
        self.lsb_stego = BarcodeSteganography()
        self.dct_stego = DCTSteganography()
        self.lsb_ratio = HYBRID_LSB_RATIO

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
            raise ValueError("Invalid hybrid stego format or magic header not found.")
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

    def hide_text_hybrid(self, cover_image_path, text, output_path):
        cover_img = Image.open(cover_image_path).convert("RGB")
        cover_array = np.array(cover_img, dtype=np.uint8)
        height, width, channels = cover_array.shape
        all_bits = self._text_to_bits(text)
        total_bits = len(all_bits)
        lsb_bits_count = int(total_bits * self.lsb_ratio)
        lsb_bits = all_bits[:lsb_bits_count]
        dct_bits = all_bits[lsb_bits_count:]
        stego_array = cover_array.copy()
        bit_index = 0
        for y in range(height):
            for x in range(width):
                if bit_index < len(lsb_bits):
                    stego_array[y, x, 0] = (stego_array[y, x, 0] & 0xFE) | lsb_bits[
                        bit_index
                    ]
                    bit_index += 1
                else:
                    break
            if bit_index >= len(lsb_bits):
                break
        dct_bit_index = 0
        block_size = 8
        for c in [1, 2]:
            channel = stego_array[:, :, c]
            for block_y in range(0, height - block_size + 1, block_size):
                for block_x in range(0, width - block_size + 1, block_size):
                    if dct_bit_index >= len(dct_bits):
                        break
                    block = channel[
                        block_y : block_y + block_size,
                        block_x : block_x + block_size,
                    ]
                    dct_block = dct(dct(block, axis=0, norm="ortho"), axis=1, norm="ortho")
                    for pos in self.dct_stego.embed_positions:
                        if dct_bit_index >= len(dct_bits):
                            break
                        i, j = pos
                        coeff = dct_block[i, j]
                        quantized = round(
                            coeff / self.dct_stego.quantization_factor
                        )
                        if dct_bits[dct_bit_index] == 1:
                            quantized = quantized | 1
                        else:
                            quantized = quantized & ~1
                        dct_block[i, j] = (
                            quantized * self.dct_stego.quantization_factor
                        )
                        dct_bit_index += 1
                    idct_block = idct(
                        idct(dct_block, axis=0, norm="ortho"), axis=1, norm="ortho"
                    )
                    stego_array[
                        block_y : block_y + block_size,
                        block_x : block_x + block_size,
                        c,
                    ] = idct_block
                if dct_bit_index >= len(dct_bits):
                    break
            if dct_bit_index >= len(dct_bits):
                break
        stego_array = np.clip(stego_array, 0, 255).astype(np.uint8)
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
        magic = MAGIC_HEADER_HYBAR
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
        lsb_bits_count = int(len(all_bits) * self.lsb_ratio)
        lsb_bits = all_bits[:lsb_bits_count]
        dct_bits = all_bits[lsb_bits_count:]
        lsb_capacity = height * width
        blocks_per_row = width // 8
        blocks_per_col = height // 8
        bits_per_block = len(self.dct_stego.embed_positions)
        dct_capacity = blocks_per_row * blocks_per_col * bits_per_block * 2
        if len(lsb_bits) > lsb_capacity or len(dct_bits) > dct_capacity:
            print("WARNING: Cover image too small for Hybrid barcode! Resizing...")
            total_needed = len(all_bits)
            needed_pixels = total_needed / 1.0
            min_dim = int(np.sqrt(needed_pixels))
            target_dim = int(min_dim * 1.5)
            print(f"Resizing from {width}x{height} to {target_dim}x{target_dim}")
            cover_img = cover_img.resize((target_dim, target_dim), Image.LANCZOS)
            cover_array = np.array(cover_img, dtype=np.float32)
            height, width, channels = cover_array.shape
        stego_array = cover_array.copy()
        bit_index = 0
        for y in range(height):
            for x in range(width):
                if bit_index < len(lsb_bits):
                    val = int(stego_array[y, x, 0])
                    stego_array[y, x, 0] = (val & 0xFE) | lsb_bits[bit_index]
                    bit_index += 1
                else:
                    break
            if bit_index >= len(lsb_bits):
                break
        dct_bit_index = 0
        block_size = 8
        for c in [1, 2]:
            channel = stego_array[:, :, c]
            for block_y in range(0, height - block_size + 1, block_size):
                for block_x in range(0, width - block_size + 1, block_size):
                    if dct_bit_index >= len(dct_bits):
                        break
                    block = channel[
                        block_y : block_y + block_size,
                        block_x : block_x + block_size,
                    ]
                    dct_block = dct(dct(block, axis=0, norm="ortho"), axis=1, norm="ortho")
                    if dct_bit_index < len(dct_bits):
                        for pos in self.dct_stego.embed_positions:
                            if dct_bit_index >= len(dct_bits):
                                break
                            i, j = pos
                            coeff = dct_block[i, j]
                            quantized = round(
                                coeff / self.dct_stego.quantization_factor
                            )
                            if dct_bits[dct_bit_index] == 1:
                                quantized = quantized | 1
                            else:
                                quantized = quantized & ~1
                            dct_block[i, j] = (
                                quantized * self.dct_stego.quantization_factor
                            )
                            dct_bit_index += 1
                    idct_block = idct(
                        idct(dct_block, axis=0, norm="ortho"), axis=1, norm="ortho"
                    )
                    stego_array[
                        block_y : block_y + block_size,
                        block_x : block_x + block_size,
                        c,
                    ] = idct_block
                if dct_bit_index >= len(dct_bits):
                    break
            if dct_bit_index >= len(dct_bits):
                break
        stego_array = np.clip(stego_array, 0, 255)
        stego_array = np.round(stego_array).astype(np.uint8)
        stego_img = Image.fromarray(stego_array, "RGB")
        if not output_path.lower().endswith(".png"):
            output_path = output_path.rsplit(".", 1)[0] + ".png"
        stego_img.save(output_path, "PNG", compress_level=6)

    def extract_text_hybrid(self, stego_image_path):
        stego_img = Image.open(stego_image_path).convert("RGB")
        stego_array = np.array(stego_img, dtype=np.float32)
        height, width, channels = stego_array.shape
        lsb_bits = []
        for y in range(height):
            for x in range(width):
                lsb_bits.append(int(stego_array[y, x, 0]) & 1)
        dct_bits = []
        block_size = 8
        for c in [1, 2]:
            channel = stego_array[:, :, c]
            for block_y in range(0, height - block_size + 1, block_size):
                for block_x in range(0, width - block_size + 1, block_size):
                    block = channel[
                        block_y : block_y + block_size,
                        block_x : block_x + block_size,
                    ]
                    dct_block = dct(
                        dct(block, axis=0, norm="ortho"), axis=1, norm="ortho"
                    )
                    for pos in self.dct_stego.embed_positions:
                        i, j = pos
                        coeff = dct_block[i, j]
                        quantized = round(
                            coeff / self.dct_stego.quantization_factor
                        )
                        dct_bits.append(quantized & 1)
        magic_header_bits = len(self.magic_header) * 8
        min_bits_needed = magic_header_bits + 32

        def bits_to_int(bits_slice):
            val = 0
            for b in bits_slice:
                val = (val << 1) | int(b)
            return val

        def try_decode_from_start(start_idx):
            # Parse length from header inside LSB stream.
            if start_idx + min_bits_needed > len(lsb_bits):
                return None
            header_len_bits = bits_to_int(
                lsb_bits[start_idx + magic_header_bits : start_idx + magic_header_bits + 32]
            )
            total_payload_bits = (len(self.magic_header) + 4 + header_len_bits) * 8
            if total_payload_bits <= 0:
                return None
            lsb_needed = int(total_payload_bits * self.lsb_ratio)
            dct_needed = max(0, total_payload_bits - lsb_needed)
            # Ensure we have enough bits for both parts.
            if start_idx + lsb_needed > len(lsb_bits) or dct_needed > len(dct_bits):
                return None
            combined = lsb_bits[start_idx : start_idx + lsb_needed] + dct_bits[:dct_needed]
            try:
                return self._bits_to_text(combined)
            except Exception:
                return None

        for start_idx in range(min(1000, len(lsb_bits) - min_bits_needed)):
            test_bits = lsb_bits[start_idx : start_idx + magic_header_bits]
            if len(test_bits) < magic_header_bits:
                continue
            bytes_test = []
            for i in range(0, len(test_bits), 8):
                if i + 8 <= len(test_bits):
                    byte_val = 0
                    for j in range(8):
                        byte_val |= test_bits[i + j] << (7 - j)
                    bytes_test.append(byte_val)
            if bytes(bytes_test).startswith(self.magic_header):
                decoded = try_decode_from_start(start_idx)
                if decoded is not None:
                    return decoded
                # Fallback attempt: sometimes full payload may be mostly in LSB.
                try:
                    return self._bits_to_text(lsb_bits[start_idx:])
                except Exception:
                    pass
        lsb_part_size = int(len(lsb_bits) * self.lsb_ratio)
        dct_part_size = min(
            len(dct_bits), int(len(lsb_bits) * (1 - self.lsb_ratio))
        )
        combined_bits = lsb_bits[:lsb_part_size] + dct_bits[:dct_part_size]
        for start_idx in range(min(1000, len(combined_bits) - min_bits_needed)):
            test_bits = combined_bits[
                start_idx : start_idx + magic_header_bits
            ]
            if len(test_bits) < magic_header_bits:
                continue
            bytes_test = []
            for i in range(0, len(test_bits), 8):
                if i + 8 <= len(test_bits):
                    byte_val = 0
                    for j in range(8):
                        byte_val |= test_bits[i + j] << (7 - j)
                    bytes_test.append(byte_val)
            if bytes(bytes_test).startswith(self.magic_header):
                try:
                    return self._bits_to_text(combined_bits[start_idx:])
                except Exception:
                    pass
        try:
            return self._bits_to_text(combined_bits)
        except Exception:
            pass
        try:
            return self._bits_to_text(lsb_bits)
        except Exception:
            raise ValueError(
                "Failed to extract hybrid stego data - magic header not found"
            )

    def extract_barcode_from_image(self, stego_image_path):
        img_format = Image.open(stego_image_path).format
        if img_format and img_format.upper() not in ["PNG", "BMP", "TIFF"]:
            raise ValueError(
                f"Hybrid method requires lossless format. Image is '{img_format}'. Please use PNG."
            )
        stego_img = Image.open(stego_image_path).convert("RGB")
        stego_array = np.array(stego_img, dtype=np.float32)
        height, width, channels = stego_array.shape
        lsb_bits = []
        for y in range(height):
            for x in range(width):
                lsb_bits.append(int(stego_array[y, x, 0]) & 1)
        dct_bits = []
        block_size = 8
        for c in [1, 2]:
            channel = stego_array[:, :, c]
            for block_y in range(0, height - block_size + 1, block_size):
                for block_x in range(0, width - block_size + 1, block_size):
                    block = channel[
                        block_y : block_y + block_size,
                        block_x : block_x + block_size,
                    ]
                    dct_block = dct(
                        dct(block, axis=0, norm="ortho"), axis=1, norm="ortho"
                    )
                    for pos in self.dct_stego.embed_positions:
                        i, j = pos
                        coeff = dct_block[i, j]
                        quantized = round(
                            coeff / self.dct_stego.quantization_factor
                        )
                        dct_bits.append(quantized & 1)
        magic = MAGIC_HEADER_HYBAR
        magic_bits = []
        for byte in magic:
            for i in range(7, -1, -1):
                magic_bits.append((byte >> i) & 1)
        start_index = -1

        def check_header(idx, bits_source):
            if idx + len(magic_bits) > len(bits_source):
                return False
            for k in range(len(magic_bits)):
                if bits_source[idx + k] != magic_bits[k]:
                    return False
            return True

        search_limit = min(len(lsb_bits), 10000)
        for i in range(0, search_limit, 1):
            if check_header(i, lsb_bits):
                start_index = i
                break
        if start_index == -1:
            raise ValueError(
                "No Hybrid barcode header found. Image might be cropped or not contain a Hybrid barcode."
            )
        current_pos = start_index + len(magic_bits)

        def extract_int(pos, bits_source, num_bits):
            val = 0
            for k in range(num_bits):
                val |= bits_source[pos + k] << (num_bits - 1 - k)
            return val

        barcode_height = extract_int(current_pos, lsb_bits, 16)
        current_pos += 16
        barcode_width = extract_int(current_pos, lsb_bits, 16)
        current_pos += 16
        scale = extract_int(current_pos, lsb_bits, 8)
        current_pos += 8
        total_payload_bits = barcode_height * barcode_width * 2
        total_bits = (current_pos - start_index) + total_payload_bits
        lsb_bits_count = int(total_bits * self.lsb_ratio)
        part1 = lsb_bits[start_index : start_index + lsb_bits_count]
        part2 = dct_bits[: total_bits - lsb_bits_count]
        all_bits = part1 + part2
        if len(all_bits) < total_bits:
            raise ValueError(
                f"Incomplete data. Expected {total_bits}, got {len(all_bits)}."
            )
        header_len = len(magic_bits) + 16 + 16 + 8
        pattern_bits = all_bits[header_len:]
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
