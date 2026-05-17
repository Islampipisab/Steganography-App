"""Image processing: denoising."""
from .denoise import apply_median_filter, apply_gaussian_filter

__all__ = [
    "apply_median_filter",
    "apply_gaussian_filter",
]
