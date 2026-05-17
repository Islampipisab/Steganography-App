"""
LSB (Least Significant Bit) steganography.
Hide/extract text or barcode pattern in image LSBs.
"""
import numpy as np
from PIL import Image

from config.settings import MAGIC_HEADER_BCSTEGO


class BarcodeSteganography:
    """Basic LSB Steganography."""

    def __init__(self):
        self.magic_header = MAGIC_HEADER_BCSTEGO

    def _text_to_bits(self, text):
        text_bytes = text.encode("utf-8")
        length = len(text_bytes)
        header = self.magic_header + length.to_bytes(4, "big")
        full_data = header + text_bytes
        bits = []
        for byte in full_data:
            for i in range(7, -1, -1):
                bits.append((byte >> i) & 1)
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
            raise ValueError("Invalid stego format - magic header not found")

        if len(bytes_data) < 12:
            raise ValueError("Incomplete header: need at least 12 bytes (8 header + 4 length)")

        length = int.from_bytes(bytes_data[8:12], "big")

        if length < 0:
            raise ValueError(f"Invalid data length: {length} (negative)")

        available_data = len(bytes_data) - 12
        if length > available_data:
            if available_data > 0:
                length = available_data
            else:
                raise ValueError(
                    f"Data length {length} exceeds available data {available_data} bytes"
                )

        text_bytes = bytes_data[12 : 12 + length]

        if len(text_bytes) == 0:
            raise ValueError("No text data found after header")

        try:
            return text_bytes.decode("utf-8")
        except UnicodeDecodeError:
            return text_bytes.decode("utf-8", errors="replace")

    def hide_text_in_image(self, cover_image_path, text, output_path):
        cover_img = Image.open(cover_image_path).convert("RGB")
        cover_array = np.array(cover_img)
        height, width, channels = cover_array.shape
        text_bits = self._text_to_bits(text)

        cover_capacity = height * width * channels
        if len(text_bits) > cover_capacity:
            needed_pixels = (len(text_bits) + channels - 1) // channels
            raise ValueError(
                f"Cover image too small!\n\n"
                f"Cover image: {width}x{height} pixels ({cover_capacity:,} bits capacity)\n"
                f"Text requires: {len(text_bits):,} bits ({needed_pixels:,} pixels)\n"
                f"Shortage: {len(text_bits) - cover_capacity:,} bits\n\n"
                f"Solution: Use a larger cover image (at least {int(np.ceil(np.sqrt(needed_pixels)))}x{int(np.ceil(np.sqrt(needed_pixels)))} pixels)"
            )

        stego_array = cover_array.copy()
        bit_index = 0

        for y in range(height):
            for x in range(width):
                for c in range(channels):
                    if bit_index < len(text_bits):
                        stego_array[y, x, c] = (stego_array[y, x, c] & 0xFE) | text_bits[
                            bit_index
                        ]
                        bit_index += 1
                    else:
                        break
                if bit_index >= len(text_bits):
                    break
            if bit_index >= len(text_bits):
                break

        stego_img = Image.fromarray(stego_array, "RGB")
        stego_img.save(output_path)

    def hide_barcode_in_image(self, cover_image_path, barcode_pattern, output_path):
        cover_img = Image.open(cover_image_path).convert("RGB")
        cover_array = np.array(cover_img, dtype=np.uint8)
        height, width, channels = cover_array.shape

        flat_pattern = barcode_pattern.reshape(-1).astype(np.uint8)
        barcode_bits = np.empty(flat_pattern.size * 2, dtype=np.uint8)
        barcode_bits[0::2] = (flat_pattern >> 1) & 1
        barcode_bits[1::2] = flat_pattern & 1

        barcode_height, barcode_width = barcode_pattern.shape
        header_bits = []
        for byte in self.magic_header:
            header_bits.extend([(byte >> i) & 1 for i in range(7, -1, -1)])
        for dim in [barcode_height, barcode_width]:
            header_bits.extend([(dim >> i) & 1 for i in range(15, -1, -1)])
        scale_factor = 10
        header_bits.extend([(scale_factor >> i) & 1 for i in range(7, -1, -1)])
        all_bits = np.concatenate([np.asarray(header_bits, dtype=np.uint8), barcode_bits])
        cover_capacity = height * width * channels

        if len(all_bits) > cover_capacity:
            print("WARNING: Cover image too small! Resizing...")
            needed_pixels = (len(all_bits) + channels - 1) // channels
            min_dim = int(np.ceil(np.sqrt(needed_pixels)))
            target_dim = int(min_dim * 1.05)
            print(f"Resizing from {width}x{height} to {target_dim}x{target_dim}")
            cover_img = cover_img.resize((target_dim, target_dim), Image.LANCZOS)
            cover_array = np.array(cover_img, dtype=np.uint8)
            height, width, channels = cover_array.shape
            cover_capacity = height * width * channels
            if len(all_bits) > cover_capacity:
                raise ValueError("Resize failed to provide enough capacity.")

        stego_array = cover_array.copy().astype(np.uint8)
        flat = stego_array.reshape(-1)
        n = len(all_bits)
        flat[:n] = (flat[:n] & 0xFE) | all_bits[:n]

        stego_array = stego_array.astype(np.uint8)
        png_path = output_path
        if not png_path.lower().endswith(".png"):
            png_path = png_path.rsplit(".", 1)[0] + ".png"

        stego_img = Image.fromarray(stego_array, "RGB")
        stego_img.save(png_path, "PNG", compress_level=6)

    def extract_text_from_image(self, stego_image_path):
        img_format = Image.open(stego_image_path).format
        if img_format and img_format.upper() in ["JPEG", "JPG"]:
            raise ValueError(
                "JPEG format detected! JPEG is a lossy format that destroys LSB steganographic data.\n"
                "Please use a lossless format like PNG, BMP, or TIFF.\n"
                "If you saved the image as JPEG after hiding data, the steganographic data is likely lost."
            )

        stego_img = Image.open(stego_image_path).convert("RGB")
        stego_array = np.array(stego_img)
        height, width, channels = stego_array.shape

        extracted_bits = []
        for y in range(height):
            for x in range(width):
                for c in range(channels):
                    extracted_bits.append(stego_array[y, x, c] & 1)

        magic_found = False
        start_index = 0
        magic_header_bits = len(self.magic_header) * 8
        min_bits_needed = magic_header_bits + 32
        max_search_bits = min(len(extracted_bits) - min_bits_needed, 500000)

        for i in range(0, max_search_bits, 8):
            if i + min_bits_needed > len(extracted_bits):
                break
            bits_at_pos = extracted_bits[i : i + magic_header_bits]
            if len(bits_at_pos) < magic_header_bits:
                continue
            bytes_at_pos = []
            for j in range(0, magic_header_bits, 8):
                if j + 8 <= len(bits_at_pos):
                    byte_val = 0
                    for k in range(8):
                        byte_val |= bits_at_pos[j + k] << (7 - k)
                    bytes_at_pos.append(byte_val)
            if bytes(bytes_at_pos).startswith(self.magic_header):
                try:
                    length_bits = extracted_bits[
                        i + magic_header_bits : i + magic_header_bits + 32
                    ]
                    if len(length_bits) < 32:
                        continue
                    length_bytes = []
                    for j in range(0, 32, 8):
                        if j + 8 <= len(length_bits):
                            byte_val = 0
                            for k in range(8):
                                byte_val |= length_bits[j + k] << (7 - k)
                            length_bytes.append(byte_val)
                    if len(length_bytes) == 4:
                        data_length = int.from_bytes(bytes(length_bytes), "big")
                        max_reasonable_length = (
                            len(extracted_bits) - i - magic_header_bits - 32
                        ) // 8
                        if 1 <= data_length <= max_reasonable_length:
                            magic_found = True
                            start_index = i
                            break
                except Exception:
                    continue

        if not magic_found:
            for i in range(0, min(max_search_bits, 10000), 1):
                if i + min_bits_needed > len(extracted_bits):
                    break
                bits_at_pos = extracted_bits[i : i + magic_header_bits]
                if len(bits_at_pos) < magic_header_bits:
                    continue
                bytes_at_pos = []
                for j in range(0, magic_header_bits, 8):
                    if j + 8 <= len(bits_at_pos):
                        byte_val = 0
                        for k in range(8):
                            byte_val |= bits_at_pos[j + k] << (7 - k)
                        bytes_at_pos.append(byte_val)
                if bytes(bytes_at_pos).startswith(self.magic_header):
                    try:
                        length_bits = extracted_bits[
                            i + magic_header_bits : i + magic_header_bits + 32
                        ]
                        if len(length_bits) >= 32:
                            length_bytes = []
                            for j in range(0, 32, 8):
                                if j + 8 <= len(length_bits):
                                    byte_val = 0
                                    for k in range(8):
                                        byte_val |= length_bits[j + k] << (7 - k)
                                    length_bytes.append(byte_val)
                            if len(length_bytes) == 4:
                                data_length = int.from_bytes(bytes(length_bytes), "big")
                                max_reasonable_length = (
                                    len(extracted_bits) - i - magic_header_bits - 32
                                ) // 8
                                if 1 <= data_length <= max_reasonable_length:
                                    magic_found = True
                                    start_index = i
                                    break
                    except Exception:
                        continue

        if not magic_found:
            raise ValueError(
                "No valid stego data found in image.\n\n"
                "Possible reasons:\n"
                "1. Image doesn't contain steganographic data\n"
                "2. Image was saved in a lossy format (JPEG) which destroyed the data\n"
                "3. Image was modified, compressed, or converted after hiding data\n"
                "4. Wrong image file selected\n"
                "5. Image was created with a different steganography method\n\n"
                "Tip: Make sure you're extracting from the exact PNG/BMP file that was created when you hid the text."
            )

        text_bits = extracted_bits[start_index:]
        return self._bits_to_text(text_bits)

    def extract_barcode_from_image(self, stego_image_path):
        img_format = Image.open(stego_image_path).format
        if img_format and img_format.upper() in ["JPEG", "JPG"]:
            print("⚠️ Warning: JPEG format detected! Extraction may fail.")

        stego_img = Image.open(stego_image_path)
        if stego_img.mode != "RGB":
            stego_img = stego_img.convert("RGB")
        stego_array = np.array(stego_img, dtype=np.uint8)
        height, width, channels = stego_array.shape

        # Vectorized LSB extraction (Python triple-loop was minutes on large mobile-upload images).
        extracted_bits = (stego_array.reshape(-1) & 1).astype(np.uint8)

        magic_found = False
        start_index = 0
        inverted = False
        magic_header_bits = len(self.magic_header) * 8

        def check_header(bits, start_idx, invert=False):
            if start_idx + magic_header_bits > len(bits):
                return False
            check_bits = bits[start_idx : start_idx + magic_header_bits]
            bytes_val = []
            for j in range(0, magic_header_bits, 8):
                byte_val = 0
                for k in range(8):
                    bit = check_bits[j + k]
                    if invert:
                        bit = 1 - bit
                    byte_val |= bit << (7 - k)
                bytes_val.append(byte_val)
            return bytes(bytes_val).startswith(self.magic_header)

        print(f"Searching {len(extracted_bits)} bits for magic header...")

        if check_header(extracted_bits, 0):
            magic_found = True
            start_index = 0
            print("Found magic header at start!")

        if not magic_found:
            search_limit = len(extracted_bits) // 2
            for i in range(0, search_limit, 8):
                if check_header(extracted_bits, i):
                    magic_found = True
                    start_index = i
                    print(f"Found magic header at bit {i} (byte aligned)")
                    break
                if check_header(extracted_bits, i, invert=True):
                    magic_found = True
                    start_index = i
                    inverted = True
                    print(f"Found INVERTED magic header at bit {i}")
                    break

        if not magic_found:
            print("Deep search initiated...")
            deep_limit = min(len(extracted_bits), 100000)
            for i in range(deep_limit):
                if check_header(extracted_bits, i):
                    magic_found = True
                    start_index = i
                    break
                if check_header(extracted_bits, i, invert=True):
                    magic_found = True
                    start_index = i
                    inverted = True
                    break

        if not magic_found:
            raise ValueError(
                "No valid barcode stego data found in image.\n"
                "Tried normal and inverted bit extraction.\n"
                "Image might be corrupted, resized, or saved in lossy format."
            )

        dim_start = start_index + magic_header_bits

        def extract_int(bits, start, length, invert):
            val = 0
            for i in range(length):
                bit = int(bits[start + i])
                if invert:
                    bit = 1 - bit
                val |= bit << (length - 1 - i)
            return val

        barcode_height = extract_int(extracted_bits, dim_start, 16, inverted)
        barcode_width = extract_int(extracted_bits, dim_start + 16, 16, inverted)
        scale_factor = 10
        current_pos = dim_start + 32
        potential_scale = extract_int(extracted_bits, current_pos, 8, inverted)
        if 1 <= potential_scale <= 50:
            scale_factor = potential_scale
            current_pos += 8

        print(f"Extracted dimensions: {barcode_width}x{barcode_height}, Scale: {scale_factor}")

        if (
            barcode_height <= 0
            or barcode_width <= 0
            or barcode_height > 10000
            or barcode_width > 10000
        ):
            raise ValueError(
                f"Invalid dimensions extracted: {barcode_width}x{barcode_height}"
            )

        pattern_size = int(barcode_height) * int(barcode_width) * 2
        if current_pos + pattern_size > len(extracted_bits):
            raise ValueError("Not enough bits for pattern content")

        pattern_bits = extracted_bits[current_pos : current_pos + pattern_size]
        pb = np.asarray(pattern_bits, dtype=np.uint8)
        if inverted:
            pb = 1 - pb
        if pb.size < barcode_height * barcode_width * 2:
            raise ValueError("Not enough bits for pattern content")
        msb = pb[0::2][: barcode_height * barcode_width]
        lsb = pb[1::2][: barcode_height * barcode_width]
        barcode_pattern = ((msb << 1) | lsb).reshape(barcode_height, barcode_width)

        self._last_extracted_scale = scale_factor
        return barcode_pattern

    def get_last_extracted_scale(self):
        return getattr(self, "_last_extracted_scale", 10)
