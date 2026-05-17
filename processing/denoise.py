"""Denoising filters for stego images."""
import numpy as np
from scipy.ndimage import median_filter, gaussian_filter


def apply_median_filter(image_array, size):
    """Apply median filter (good for salt and pepper noise)."""
    if len(image_array.shape) == 3:
        filtered = np.zeros_like(image_array)
        for c in range(image_array.shape[2]):
            filtered[:, :, c] = median_filter(image_array[:, :, c], size=size)
        return filtered
    return median_filter(image_array, size=size)


def apply_gaussian_filter(image_array, sigma):
    """Apply Gaussian filter (good for general noise)."""
    if len(image_array.shape) == 3:
        filtered = np.zeros_like(image_array)
        for c in range(image_array.shape[2]):
            filtered[:, :, c] = gaussian_filter(
                image_array[:, :, c], sigma=sigma
            )
        return filtered
    return gaussian_filter(image_array, sigma=sigma)
