"""Image quality metrics: PSNR, SSIM, BER, entropy, chi-square."""
import numpy as np
from PIL import Image
from skimage.metrics import structural_similarity as ssim


class QualityMetrics:
    """Calculate image quality metrics."""

    @staticmethod
    def calculate_psnr(original, stego):
        original = np.array(original, dtype=np.float64)
        stego = np.array(stego, dtype=np.float64)
        mse = np.mean((original - stego) ** 2)
        if mse == 0:
            return float("inf")
        return 20 * np.log10(255.0 / np.sqrt(mse))

    @staticmethod
    def calculate_ssim(original, stego):
        original = np.array(original, dtype=np.float64)
        stego = np.array(stego, dtype=np.float64)
        if len(original.shape) == 3:
            original_gray = np.mean(original, axis=2)
            stego_gray = np.mean(stego, axis=2)
        else:
            original_gray = original
            stego_gray = stego
        return ssim(original_gray, stego_gray, data_range=255)

    @staticmethod
    def calculate_ber(original, stego):
        original = np.array(original, dtype=np.uint8)
        stego = np.array(stego, dtype=np.uint8)
        bit_diff = np.bitwise_xor(original, stego)
        total_bits = original.size * 8
        inverted_bits = np.sum(np.unpackbits(bit_diff))
        return (inverted_bits / total_bits) * 100

    @staticmethod
    def calculate_entropy(image_array):
        if len(image_array.shape) == 3:
            image_array = np.mean(image_array, axis=2)
        hist, _ = np.histogram(image_array.flatten(), bins=256, range=(0, 256))
        hist = hist.astype(np.float64)
        hist = hist / hist.sum()
        hist = hist[hist > 0]
        return -np.sum(hist * np.log2(hist))

    @staticmethod
    def calculate_histogram_stats(image_array):
        if len(image_array.shape) == 3:
            image_array = np.mean(image_array, axis=2)
        hist, _ = np.histogram(image_array.flatten(), bins=256, range=(0, 256))
        return {
            "mean": np.mean(hist),
            "std": np.std(hist),
            "variance": np.var(hist),
            "max": np.max(hist),
            "min": np.min(hist),
        }

    @staticmethod
    def chi_square_test_lsb(image_array):
        if len(image_array.shape) == 3:
            image_array = np.mean(image_array, axis=2).astype(np.uint8)
        else:
            image_array = image_array.astype(np.uint8)
        even_pairs = 0
        odd_pairs = 0
        flat = image_array.flatten()
        for i in range(len(flat) - 1):
            if flat[i] % 2 == 0 and flat[i + 1] % 2 == 0:
                even_pairs += 1
            elif flat[i] % 2 == 1 and flat[i + 1] % 2 == 1:
                odd_pairs += 1
        total_pairs = even_pairs + odd_pairs
        if total_pairs == 0:
            return 1.0
        expected = total_pairs / 2.0
        chi_square = ((even_pairs - expected) ** 2 / expected) + (
            (odd_pairs - expected) ** 2 / expected
        )
        return min(1.0, chi_square / 10.0)

    @staticmethod
    def calculate_all_metrics(original_path, stego_path):
        original_img = Image.open(original_path).convert("RGB")
        stego_img = Image.open(stego_path).convert("RGB")
        if original_img.size != stego_img.size:
            stego_img = stego_img.resize(original_img.size, Image.LANCZOS)
        original_array = np.array(original_img)
        stego_array = np.array(stego_img)
        psnr = QualityMetrics.calculate_psnr(original_img, stego_img)
        ssim_value = QualityMetrics.calculate_ssim(original_img, stego_img)
        ber = QualityMetrics.calculate_ber(original_img, stego_img)
        entropy_original = QualityMetrics.calculate_entropy(original_array)
        entropy_stego = QualityMetrics.calculate_entropy(stego_array)
        hist_original = QualityMetrics.calculate_histogram_stats(original_array)
        hist_stego = QualityMetrics.calculate_histogram_stats(stego_array)
        chi_suspicion = QualityMetrics.chi_square_test_lsb(stego_array)
        return {
            "PSNR": psnr,
            "SSIM": ssim_value,
            "BER": ber,
            "Entropy_Original": entropy_original,
            "Entropy_Stego": entropy_stego,
            "Hist_Original": hist_original,
            "Hist_Stego": hist_stego,
            "Chi_Square_Suspicion": chi_suspicion,
        }
