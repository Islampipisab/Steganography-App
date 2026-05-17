"""
Custom barcode encoding/decoding with optional hybrid cryptography.
"""
import struct
import base64
import json
import zlib
import numpy as np
from PIL import Image

from config.settings import (
    MAGIC_HEADER_CBS,
    MAGIC_HEADER_PASSWORD,
    CBS_BLOCK_SIZE,
    BLOCK_ENCRYPTION_PERCENTAGE,
    DEFAULT_BARCODE_SCALE,
)
from crypto import HybridCrypto, SecureEncryption
from core import BarcodeSteganography

class CustomBarcodeSteganography:
    """Custom Barcode Encoding/Decoding with Hybrid Cryptography"""
    def __init__(self, use_hybrid_crypto=True):
        self.block_size = CBS_BLOCK_SIZE
        self.error_correction_level = 2
        self.magic_header = MAGIC_HEADER_CBS
        self.version = 1
        self.use_hybrid_crypto = use_hybrid_crypto
        self.hybrid_crypto = None
        if use_hybrid_crypto:
            # Try to load existing keys, or generate new ones
            try:
                private_key, public_key = HybridCrypto.load_rsa_keys()
                self.hybrid_crypto = HybridCrypto(rsa_public_key=public_key, rsa_private_key=private_key)
            except (FileNotFoundError, IOError):
                # Generate new keys if not found
                self.hybrid_crypto = HybridCrypto()
                # Save keys for future use
                self.hybrid_crypto.save_rsa_keys()
        
    def _text_to_bits(self, text):
        text_bytes = text.encode('utf-8')
        length = len(text_bytes)
        header = self.magic_header + struct.pack('>I', length)
        full_data = header + text_bytes
        bits = []
        for byte in full_data:
            for i in range(7, -1, -1):
                bits.append((byte >> i) & 1)
        return bits
    
    def _bits_to_text(self, bits):
        if len(bits) < 32:
            raise ValueError("Invalid barcode data")
        
        bytes_data = []
        for i in range(0, len(bits), 8):
            if i + 8 <= len(bits):
                byte_val = 0
                for j in range(8):
                    byte_val |= (bits[i + j] << (7 - j))
                bytes_data.append(byte_val)
        
        bytes_data = bytes(bytes_data)
        
        if not bytes_data.startswith(self.magic_header):
            raise ValueError("Invalid barcode format")
        
        length = struct.unpack('>I', bytes_data[4:8])[0]
        
        # Check if we have enough data
        available_data = len(bytes_data) - 8
        if length > available_data:
            # Data was truncated - use all available data
            print(f"Warning: Expected {length} bytes, but only {available_data} available. Using available data.")
            length = available_data
        
        text_bytes = bytes_data[8:8+length]
        try:
            return text_bytes.decode('utf-8')
        except UnicodeDecodeError:
            # Try with error handling for invalid UTF-8 bytes
            return text_bytes.decode('utf-8', errors='replace')
    
    def _add_error_correction(self, bits):
        corrected_bits = []
        for i in range(0, len(bits), self.block_size):
            block = bits[i:i+self.block_size]
            while len(block) < self.block_size:
                block.append(0)
            parity = sum(block) % 2
            block.append(parity)
            checksum = sum(block) % 2
            block.append(checksum)
            corrected_bits.extend(block)
        return corrected_bits
    
    def _remove_error_correction(self, bits):
        corrected_bits = []
        for i in range(0, len(bits), self.block_size + 2):
            if i + self.block_size + 2 > len(bits):
                break
            block = bits[i:i+self.block_size+2]
            data_block = block[:self.block_size]
            corrected_bits.extend(data_block)
        return corrected_bits
    
    def _create_pattern(self, bits):
        total_bits = len(bits)
        width = int(np.ceil(np.sqrt(total_bits * 2)))
        height = int(np.ceil(total_bits * 2 / width))
        
        pattern = np.zeros((height, width), dtype=np.uint8)
        pattern[0, :] = 1
        pattern[:, 0] = 1
        pattern[-1, :] = 1
        pattern[:, -1] = 1
        pattern[0, 0] = 0
        pattern[0, -1] = 0
        pattern[-1, 0] = 0
        pattern[-1, -1] = 0
        
        bit_index = 0
        for row in range(1, height-1):
            for col in range(1, width-1):
                if bit_index < len(bits):
                    pattern[row, col] = bits[bit_index] + 2
                    bit_index += 1
                else:
                    break
            if bit_index >= len(bits):
                break
        
        return pattern
    
    def _extract_pattern(self, pattern):
        height, width = pattern.shape
        bits = []
        # Extract bits from inner area (skip border)
        # Pattern structure: border=1, corners=0, data=2 or 3
        for row in range(1, height-1):
            for col in range(1, width-1):
                # Only extract from positions that have data (value 2 or 3)
                # Value 0 or 1 are border/corner markers
                pixel_value = pattern[row, col]
                if pixel_value >= 2:
                    # Extract bit: 2 → bit 0, 3 → bit 1
                    bits.append(pixel_value - 2)
        return bits
    
    def encode(self, text, use_hybrid_encryption=None):
        """
        Encode text into barcode pattern with optional hybrid encryption
        
        Args:
            text: Text to encode
            use_hybrid_encryption: Override default hybrid encryption setting (optional)
        """
        # Apply hybrid encryption if enabled
        if use_hybrid_encryption is None:
            use_hybrid_encryption = self.use_hybrid_crypto
        
        if use_hybrid_encryption and self.hybrid_crypto:
            # For image data, use BLOCK encryption (encrypt only a portion of data)
            # This provides security while keeping data size manageable
            if text.startswith("[IMAGE:") and len(text) > 5000:
                lines = text.split('\n', 1)
                if len(lines) == 2:
                    header = lines[0]  # [IMAGE:filename:format:dimensions]
                    img_base64 = lines[1]  # base64 image data
                    
                    # Configurable block encryption percentage (default: 20%)
                    # Encrypting 20% provides good security for most images while saving 80% space
                    # You can adjust this: 10% = //10, 30% = //3.33, 50% = //2
                    encryption_percentage = BLOCK_ENCRYPTION_PERCENTAGE  # Encrypt first 20% of image data
                    block_size = len(img_base64) * encryption_percentage // 100
                    encrypted_part = img_base64[:block_size]
                    plain_part = img_base64[block_size:]
                    
                    # Encrypt the block
                    encrypted_package = self.hybrid_crypto.encrypt_hybrid(encrypted_part)
                    json_str = json.dumps(encrypted_package)
                    compressed = zlib.compress(json_str.encode('utf-8'), level=9)
                    compressed_b64 = base64.b64encode(compressed).decode('utf-8')
                    
                    # Format: header + [BLOCK_ENC:size]encrypted|||plain
                    text = f"{header}\n[BLOCK_ENC:{block_size}]{compressed_b64}|||{plain_part}"
                    
                    # Calculate size savings
                    original_size = len(img_base64)
                    encrypted_size = len(compressed_b64)
                    plain_size = len(plain_part)
                    total_size = len(compressed_b64) + len(plain_part) + len(header) + 20
                    savings_percent = (1 - total_size / (original_size * 3)) * 100  # Compared to full encryption
                    
                    print(f"✅ Block encryption ({encryption_percentage}%):")
                    print(f"   • Original image data: {original_size:,} chars")
                    print(f"   • Encrypted block: {encrypted_size:,} chars ({encryption_percentage}% of image)")
                    print(f"   • Plain text: {plain_size:,} chars ({100-encryption_percentage}% of image)")
                    print(f"   • Total size: {total_size:,} chars")
                    print(f"   • Space saved vs full encryption: ~{savings_percent:.0f}%")
                else:
                    # Can't split, use compressed encryption
                    encrypted_package = self.hybrid_crypto.encrypt_hybrid(text)
                    json_str = json.dumps(encrypted_package)
                    compressed = zlib.compress(json_str.encode('utf-8'), level=9)
                    compressed_b64 = base64.b64encode(compressed).decode('utf-8')
                    text = "[HYBRID_ENCRYPTED_COMPRESSED]" + compressed_b64
            else:
                # Small data - use normal compressed encryption
                encrypted_package = self.hybrid_crypto.encrypt_hybrid(text)
                json_str = json.dumps(encrypted_package)
                compressed = zlib.compress(json_str.encode('utf-8'), level=9)
                compressed_b64 = base64.b64encode(compressed).decode('utf-8')
                text = "[HYBRID_ENCRYPTED_COMPRESSED]" + compressed_b64
        
        bits = self._text_to_bits(text)
        
        # Skip error correction for encrypted data (encryption provides integrity)
        # Error correction doubles the size, causing issues with large encrypted images
        if "[HYBRID_ENCRYPTED" in text:
            # Encrypted data - skip error correction to save space
            print(f"Encoding encrypted data: {len(text)} chars, {len(bits)} bits")
            pattern = self._create_pattern(bits)
            print(f"Created pattern: {pattern.shape[0]}x{pattern.shape[1]} = {pattern.shape[0]*pattern.shape[1]} cells")
        else:
            # Non-encrypted data - use error correction
            corrected_bits = self._add_error_correction(bits)
            pattern = self._create_pattern(corrected_bits)
        
        return pattern
    
    def decode(self, pattern, use_hybrid_decryption=None):
        """
        Decode barcode pattern to text with optional hybrid decryption
        
        Args:
            pattern: Barcode pattern to decode
            use_hybrid_decryption: Override default hybrid decryption setting (optional)
        """
        # Validate pattern
        if pattern is None or pattern.size == 0:
            raise ValueError("Invalid barcode pattern: pattern is empty or None")
        
        if pattern.shape[0] < 3 or pattern.shape[1] < 3:
            raise ValueError(f"Invalid barcode pattern: too small ({pattern.shape[0]}x{pattern.shape[1]}), need at least 3x3")
        
        extracted_bits = self._extract_pattern(pattern)
        
        if len(extracted_bits) == 0:
            raise ValueError("No data bits found in barcode pattern. Pattern may be corrupted or empty.")
        
        # Try to convert bits to text to check if it's encrypted
        # If encrypted, skip error correction removal
        print(f"Extracted {len(extracted_bits)} bits from pattern {pattern.shape}")
        
        bits = None
        text = None
        
        # Attempt 1: Try direct conversion (maybe it's encrypted and has no error correction)
        try:
            test_text = self._bits_to_text(extracted_bits)
            print(f"Decoded {len(test_text)} characters (direct)")
            if "[HYBRID_ENCRYPTED" in test_text:
                print("Detected encrypted data - skipping error correction removal")
                bits = extracted_bits
                text = test_text
        except Exception:
            pass
        
        # Attempt 2: If direct conversion failed or didn't look encrypted, try removing error correction
        if bits is None:
            try:
                print("Trying error correction removal...")
                bits = self._remove_error_correction(extracted_bits)
                text = self._bits_to_text(bits)
            except Exception as e:
                # Attempt 3: If that failed, maybe it WAS encrypted but header was slightly corrupted?
                # Or maybe error correction failed?
                print(f"Error correction removal failed: {e}")
                if len(extracted_bits) > 32:
                    # Last resort: try to interpret as raw bits if we have enough
                    bits = extracted_bits
        
        if bits is None or len(bits) < 32:
             raise ValueError(f"Not enough valid bits extracted ({len(bits) if bits else 0} bits). Barcode pattern may be corrupted.")
        
        # If we haven't successfully decoded text yet, try one last time
        if text is None:
            try:
                text = self._bits_to_text(bits)
            except Exception as e:
                raise ValueError(f"Failed to decode text from bits: {e}. The barcode pattern might be corrupted.")
        
        # Check if data is hybrid encrypted and decrypt if needed
        if use_hybrid_decryption is None:
            use_hybrid_decryption = self.use_hybrid_crypto
        
        # Only try hybrid decryption if explicitly enabled and we have the crypto object
        if use_hybrid_decryption and self.hybrid_crypto:
            # Check for block encryption format (first N% encrypted, rest plain)
            if "[BLOCK_ENC:" in text:
                try:
                    # Split into header and data
                    lines = text.split('\n', 1)
                    if len(lines) == 2:
                        header = lines[0]  # [IMAGE:filename:format:dimensions]
                        data_part = lines[1]  # [BLOCK_ENC:size]encrypted|||plain
                        
                        # Extract block size, encrypted part, and plain part
                        if data_part.startswith("[BLOCK_ENC:"):
                            # Parse: [BLOCK_ENC:size]encrypted|||plain
                            block_marker_end = data_part.index("]")
                            block_marker = data_part[:block_marker_end+1]
                            block_size = int(block_marker.split(":")[1].replace("]", ""))
                            
                            # Split encrypted and plain parts
                            remaining = data_part[block_marker_end+1:]
                            parts = remaining.split("|||", 1)
                            
                            if len(parts) == 2:
                                encrypted_b64 = parts[0]
                                plain_part = parts[1]
                                
                                # Decrypt the encrypted block
                                compressed = base64.b64decode(encrypted_b64)
                                json_str = zlib.decompress(compressed).decode('utf-8')
                                encrypted_package = json.loads(json_str)
                                decrypted_block = self.hybrid_crypto.decrypt_hybrid(encrypted_package).decode('utf-8')
                                
                                # Reconstruct: header + decrypted_block + plain_part
                                text = f"{header}\n{decrypted_block}{plain_part}"
                                print(f"✅ Block decryption successful: {len(decrypted_block)} chars decrypted, {len(plain_part)} chars plain")
                except Exception as e:
                    print(f"❌ Block decryption error: {e}")
                    pass
            # Check for partial encryption format (header only encrypted)
            elif text.startswith("[HYBRID_PARTIAL_ENCRYPTED]"):
                try:
                    # Split into encrypted header and plain base64 data
                    parts = text.split('\n', 1)
                    if len(parts) == 2:
                        encrypted_header_part = parts[0][len("[HYBRID_PARTIAL_ENCRYPTED]"):]
                        img_base64 = parts[1]
                        
                        # Decrypt header
                        compressed = base64.b64decode(encrypted_header_part)
                        json_str = zlib.decompress(compressed).decode('utf-8')
                        encrypted_package = json.loads(json_str)
                        decrypted_header = self.hybrid_crypto.decrypt_hybrid(encrypted_package).decode('utf-8')
                        
                        # Reconstruct: decrypted header + plain base64 data
                        text = f"{decrypted_header}\n{img_base64}"
                        print("Partial decryption successful")
                except Exception as e:
                    print(f"Partial decryption error: {e}")
                    pass
            # Check for chunked encrypted format (for large images)
            elif text.startswith("[HYBRID_ENCRYPTED_CHUNKED:"):
                try:
                    # Extract number of chunks and data
                    marker_end = text.index("]")
                    marker = text[:marker_end+1]
                    num_chunks = int(marker.split(":")[1].replace("]", ""))
                    combined_data = text[marker_end+1:]
                    
                    # Split into chunks
                    chunk_strings = combined_data.split("|||")
                    
                    if len(chunk_strings) != num_chunks:
                        raise ValueError(f"Expected {num_chunks} chunks, got {len(chunk_strings)}")
                    
                    # Decrypt each chunk
                    decrypted_chunks = []
                    for chunk_b64 in chunk_strings:
                        # Decompress
                        compressed = base64.b64decode(chunk_b64)
                        json_str = zlib.decompress(compressed).decode('utf-8')
                        # Parse JSON
                        encrypted_package = json.loads(json_str)
                        # Decrypt
                        decrypted_data = self.hybrid_crypto.decrypt_hybrid(encrypted_package)
                        decrypted_chunks.append(decrypted_data.decode('utf-8'))
                    
                    # Combine decrypted chunks
                    text = "".join(decrypted_chunks)
                except Exception as e:
                    # If decryption fails, return error
                    print(f"Chunked decryption error: {e}")
                    pass
            # Check for compressed format
            elif text.startswith("[HYBRID_ENCRYPTED_COMPRESSED]"):
                try:
                    # Remove marker and decode base64
                    compressed_b64 = text[len("[HYBRID_ENCRYPTED_COMPRESSED]"):]
                    compressed = base64.b64decode(compressed_b64)
                    # Decompress
                    json_str = zlib.decompress(compressed).decode('utf-8')
                    # Parse JSON
                    encrypted_package = json.loads(json_str)
                    # Decrypt using hybrid cryptography
                    decrypted_data = self.hybrid_crypto.decrypt_hybrid(encrypted_package)
                    text = decrypted_data.decode('utf-8')
                except Exception as e:
                    print(f"Compressed decryption error: {e}")
                    pass
            # Check for old uncompressed format
            elif text.startswith("[HYBRID_ENCRYPTED]"):
                try:
                    # Remove marker and parse JSON
                    encrypted_json = text[len("[HYBRID_ENCRYPTED]"):]
                    encrypted_package = json.loads(encrypted_json)
                    # Decrypt using hybrid cryptography
                    decrypted_data = self.hybrid_crypto.decrypt_hybrid(encrypted_package)
                    text = decrypted_data.decode('utf-8')
                except Exception as e:
                    print(f"Uncompressed decryption error: {e}")
                    pass
        
        return text
    
    def save_barcode(self, pattern, filename, scale=None):
        """
        Save barcode pattern as an image.
        
        Args:
            pattern: 2D numpy array with barcode pattern (values 0-3)
            filename: Output filename
            scale: Scale factor (default: 10). If None, uses default scale of 10.
                   The scale determines how many pixels each pattern cell occupies.
        """
        if scale is None:
            scale = DEFAULT_BARCODE_SCALE  # Default scale factor
        height, width = pattern.shape
        scaled_pattern = np.repeat(np.repeat(pattern, scale, axis=0), scale, axis=1)
        scaled_pattern = scaled_pattern * 85
        # Ensure values are exactly 0, 85, 170, or 255
        scaled_pattern = np.clip(scaled_pattern, 0, 255).astype(np.uint8)
        img = Image.fromarray(scaled_pattern, mode='L')
        # Save as PNG with no compression to preserve exact pixel values
        if not filename.lower().endswith('.png'):
            filename = filename.rsplit('.', 1)[0] + '.png'
        img.save(filename, 'PNG', compress_level=0)
    
    def load_barcode(self, filename):
        img = Image.open(filename).convert('L')
        img_array = np.array(img)
        scale = 10
        height, width = img_array.shape
        pattern_height = height // scale
        pattern_width = width // scale
        pattern = np.zeros((pattern_height, pattern_width), dtype=np.uint8)
        
        # Use average of a small region around center for more robust reading
        for i in range(pattern_height):
            for j in range(pattern_width):
                y_start = i * scale
                x_start = j * scale
                y_end = min(y_start + scale, height)
                x_end = min(x_start + scale, width)
                
                # Sample a small region (center 3x3 pixels) for more accuracy
                center_y = y_start + scale // 2
                center_x = x_start + scale // 2
                
                if center_y < height and center_x < width:
                    # Get average of center region to handle slight variations
                    region = img_array[max(0, center_y-1):min(height, center_y+2), 
                                      max(0, center_x-1):min(width, center_x+2)]
                    avg_value = np.mean(region)
                    
                    # Convert pixel value back to pattern value (0-3)
                    # Saved values are: 0, 85, 170, 255
                    # Use thresholds to handle slight variations
                    if avg_value < 43:  # 0-42 → 0
                        pattern[i, j] = 0
                    elif avg_value < 128:  # 43-127 → 1
                        pattern[i, j] = 1
                    elif avg_value < 213:  # 128-212 → 2
                        pattern[i, j] = 2
                    else:  # 213-255 → 3
                        pattern[i, j] = 3
        
        return pattern

    def hide_in_cover_image(self, text, cover_image_path, output_path):
        pattern = self.encode(text)
        stego = BarcodeSteganography()
        stego.hide_barcode_in_image(cover_image_path, pattern, output_path)
        return pattern
    
    def extract_from_stego_image(self, stego_image_path):
        stego = BarcodeSteganography()
        pattern = stego.extract_barcode_from_image(stego_image_path)
        # Try decoding without hybrid decryption first (most barcodes aren't hybrid encrypted)
        # If the text starts with [HYBRID_ENCRYPTED], we can try hybrid decryption separately
        try:
            text = self.decode(pattern, use_hybrid_decryption=False)
            # If result looks like hybrid encrypted data, try with hybrid decryption
            if text.startswith("[HYBRID_ENCRYPTED]") and self.hybrid_crypto:
                try:
                    text = self.decode(pattern, use_hybrid_decryption=True)
                except:
                    # If hybrid decryption fails, return the original text
                    pass
        except Exception as e:
            # If decoding fails, try with hybrid decryption enabled (in case it's needed)
            try:
                text = self.decode(pattern, use_hybrid_decryption=True)
            except:
                # Re-raise the original error if both attempts fail
                raise e
        return text
    
    def hide_text_directly(self, text, cover_image_path, output_path):
        stego = BarcodeSteganography()
        stego.hide_text_in_image(cover_image_path, text, output_path)
    
    def extract_text_directly(self, stego_image_path):
        stego = BarcodeSteganography()
        text = stego.extract_text_from_image(stego_image_path)
        return text

    
    def hide_text_with_password(self, text, password, cover_image_path, output_path):
        """Hide encrypted text in cover image"""
        encrypt = SecureEncryption()
        encrypted_data = encrypt.encrypt_data(text, password)
        stego = BarcodeSteganography()
        # Convert encrypted bytes to bits
        encrypted_bits = []
        for byte in encrypted_data:
            for i in range(7, -1, -1):
                encrypted_bits.append((byte >> i) & 1)
        
        # Add magic header and length for password-protected data
        magic_header = MAGIC_HEADER_PASSWORD
        header_bits = []
        for byte in magic_header:
            for i in range(7, -1, -1):
                header_bits.append((byte >> i) & 1)
        
        # Add length header (4 bytes = 32 bits)
        length = len(encrypted_data)
        length_bits = []
        for i in range(31, -1, -1):
            length_bits.append((length >> i) & 1)
        
        all_bits = header_bits + length_bits + encrypted_bits
        
        cover_img = Image.open(cover_image_path).convert('RGB')
        cover_array = np.array(cover_img)
        height, width, channels = cover_array.shape
        
        cover_capacity = height * width * channels
        if len(all_bits) > cover_capacity:
            needed_pixels = (len(all_bits) + channels - 1) // channels
            min_size = int(np.ceil(np.sqrt(needed_pixels)))
            raise ValueError(
                f"Cover image too small for password-protected text!\n\n"
                f"Cover image: {width}x{height} pixels ({cover_capacity:,} bits capacity)\n"
                f"Encrypted text requires: {len(all_bits):,} bits ({needed_pixels:,} pixels)\n"
                f"Shortage: {len(all_bits) - cover_capacity:,} bits\n\n"
                f"Solution: Use a larger cover image (at least {min_size}x{min_size} pixels)"
            )
        
        stego_array = cover_array.copy()
        bit_index = 0
        
        for y in range(height):
            for x in range(width):
                for c in range(channels):
                    if bit_index < len(all_bits):
                        stego_array[y, x, c] = (stego_array[y, x, c] & 0xFE) | all_bits[bit_index]
                        bit_index += 1
                    else:
                        break
                if bit_index >= len(all_bits):
                    break
            if bit_index >= len(all_bits):
                break
        
        stego_img = Image.fromarray(stego_array, 'RGB')
        stego_img.save(output_path)
    
    def extract_text_with_password(self, stego_image_path, password):
        """Extract and decrypt text from stego image"""
        stego_img = Image.open(stego_image_path).convert('RGB')
        stego_array = np.array(stego_img)
        height, width, channels = stego_array.shape
        
        extracted_bits = []
        for y in range(height):
            for x in range(width):
                for c in range(channels):
                    extracted_bits.append(stego_array[y, x, c] & 1)
        
        # Look for magic header (7 bytes = 56 bits)
        magic_header = MAGIC_HEADER_PASSWORD
        magic_bytes_length = len(magic_header)  # 7 bytes
        magic_bits_length = magic_bytes_length * 8  # 56 bits
        magic_found = False
        start_index = 0
        
        for i in range(len(extracted_bits) - magic_bits_length):
            bits_at_pos = extracted_bits[i:i+magic_bits_length]
            bytes_at_pos = []
            
            # Convert bits to bytes for the magic header
            for j in range(0, magic_bits_length, 8):
                if j + 8 <= len(bits_at_pos):
                    byte_val = 0
                    for k in range(8):
                        byte_val |= (bits_at_pos[j + k] << (7 - k))
                    bytes_at_pos.append(byte_val)
            
            if bytes(bytes_at_pos) == magic_header:
                magic_found = True
                start_index = i
                break
        
        if not magic_found:
            raise ValueError("No password-protected data found in image")
        
        # Extract length (4 bytes = 32 bits after magic header)
        length_start = start_index + magic_bits_length
        length_bits = extracted_bits[length_start:length_start + 32]
        
        # Convert bits to bytes first, then to integer
        length_bytes = []
        for i in range(0, 32, 8):
            if i + 8 <= len(length_bits):
                byte_val = 0
                for j in range(8):
                    byte_val |= (length_bits[i + j] << (7 - j))
                length_bytes.append(byte_val)
        
        # Unpack as big-endian unsigned int
        data_length = struct.unpack('>I', bytes(length_bytes))[0]
        
        # Safety check - encrypted data should be at least 32 bytes (salt + iv) and reasonable maximum
        max_possible_bits = len(extracted_bits) - length_start - 32
        max_possible_bytes = max_possible_bits // 8
        if data_length > max_possible_bytes or data_length < 32:
            raise ValueError(f"Invalid encrypted data length: {data_length}. Expected 32-{max_possible_bytes} bytes, got {data_length}")
        
        # Extract exactly the specified number of encrypted bytes
        encrypted_start = length_start + 32
        encrypted_bit_count = data_length * 8
        
        if encrypted_start + encrypted_bit_count > len(extracted_bits):
            raise ValueError(f"Cannot extract {encrypted_bit_count} bits starting at {encrypted_start}, only {len(extracted_bits)} bits available")
        
        encrypted_bits = extracted_bits[encrypted_start:encrypted_start + encrypted_bit_count]
        
        encrypted_bytes = []
        for i in range(0, len(encrypted_bits), 8):
            if i + 8 <= len(encrypted_bits):
                byte_val = 0
                for j in range(8):
                    byte_val |= (encrypted_bits[i + j] << (7 - j))
                encrypted_bytes.append(byte_val)
        
        encrypted_bytes = bytes(encrypted_bytes)
        
        if len(encrypted_bytes) < 32:
            raise ValueError(f"Not enough encrypted data: got {len(encrypted_bytes)} bytes, need at least 32")
        
        # Decrypt
        encrypt = SecureEncryption()
        decrypted_text = encrypt.decrypt_data(encrypted_bytes, password)
        return decrypted_text

# ============================================
# GUI APPLICATION
# ============================================
