"""
Steganography System - GUI Application.
"""
import os
import re
import struct
import io
import base64
import hashlib
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import numpy as np
from PIL import Image, ImageTk

from config.settings import MAX_IMAGE_PIXELS
from core import BarcodeSteganography, DCTSteganography, HybridSteganography
from crypto import HybridCrypto
from barcode import CustomBarcodeSteganography
from metrics import QualityMetrics
from processing import apply_median_filter, apply_gaussian_filter

# Increase PIL image size limit
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

class BarcodeSteganographyApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Steganography System")
        self.root.geometry("1000x700")
        self.root.configure(bg='lightgray')
        
        self.cbs = CustomBarcodeSteganography()
        
        # Auto-load or generate persistent RSA keys
        try:
            # Try to load existing keys
            if os.path.exists('private_key.pem') and os.path.exists('public_key.pem'):
                priv, pub = HybridCrypto.load_rsa_keys()
                self.cbs.hybrid_crypto = HybridCrypto(pub, priv)
                print("✅ Loaded existing RSA keys from disk")
            else:
                # Generate new keys and save them
                self.cbs.hybrid_crypto = HybridCrypto()
                self.cbs.hybrid_crypto.save_rsa_keys()
                print("🔑 Generated new RSA keys and saved to disk")
        except Exception as e:
            print(f"⚠️ Key loading/generation error: {e}")
            # Fall back to in-memory keys
            self.cbs.hybrid_crypto = HybridCrypto()
        
        self.dct_stego = DCTSteganography()  # Normal mode
        self.dct_stego_jpeg = DCTSteganography(jpeg_robust_mode=True)  # JPEG-robust mode
        self.hybrid_stego = HybridSteganography()
        self.current_pattern = None
        self.barcode_stego = BarcodeSteganography()
        self.current_cover_path = None  # Store cover path for quality metrics
        self.current_cover_path2 = None  # Store cover path for hide barcode quality metrics
        self.extracted_barcode_pattern = None  # Store extracted barcode pattern for saving
        self.extracted_barcode_scale = 10  # Store scale factor for extracted barcode (default 10)
        self.decoded_image = None  # Store decoded original image for saving
        self.hide_barcode_cover_preview_frame = None  # Preview frame for cover image
        self.hide_barcode_stego_preview_frame = None  # Preview frame for stego image
        self.hide_barcode_cover_image_ref = None  # Keep reference to cover image
        self.hide_barcode_stego_image_ref = None  # Keep reference to stego image
        self.denoised_image_path = None  # Store path to denoised image for extraction
        self.embedded_data_size_bytes = 0  # Store embedded data size in bytes
        
        self.setup_ui()
        print("Steganography App ready!")
    
    def setup_ui(self):
        main_frame = tk.Frame(self.root, bg='white', relief='raised', bd=2)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        title = tk.Label(main_frame, text="Steganography System", 
                        font=('Arial', 16, 'bold'), bg='white', fg='black')
        title.pack(pady=20)
        
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        encode_frame = tk.Frame(notebook, bg='white')
        notebook.add(encode_frame, text="Encode")
        self.setup_encode(encode_frame)
        
        decode_frame = tk.Frame(notebook, bg='white')
        notebook.add(decode_frame, text="Decode")
        self.setup_decode(decode_frame)
        
        stego_frame = tk.Frame(notebook, bg='white')
        notebook.add(stego_frame, text="Steganography")
        self.setup_stego(stego_frame)
        
        hide_barcode_frame = tk.Frame(notebook, bg='white')
        notebook.add(hide_barcode_frame, text="Hide Existing Barcode")
        self.setup_hide_barcode(hide_barcode_frame)
        
        extract_frame = tk.Frame(notebook, bg='white')
        notebook.add(extract_frame, text="Extract from Stego")
        self.setup_extract_stego(extract_frame)
        
        # Add diagnostic tab
        diagnostic_frame = tk.Frame(notebook, bg='white')
        notebook.add(diagnostic_frame, text="🔧 Diagnostic Tool")
        self.setup_diagnostic(diagnostic_frame)
    
    def setup_encode(self, parent):
        tk.Label(parent, text="Enter text to encode:", 
                font=('Arial', 12, 'bold'), bg='white', fg='black').pack(anchor='w', padx=20, pady=(20,5))
        
        # Input source selection frame
        input_source_frame = tk.Frame(parent, bg='white')
        input_source_frame.pack(fill=tk.X, padx=20, pady=5)
        
        tk.Button(input_source_frame, text="📝 Enter Text", bg='lightblue', fg='black', 
                 font=('Arial', 10, 'bold'), command=self.enter_text).pack(side=tk.LEFT, padx=5)
        
        tk.Button(input_source_frame, text="🖼️ Enter Photo", bg='lightgreen', fg='black', 
                 font=('Arial', 10, 'bold'), command=self.enter_photo).pack(side=tk.LEFT, padx=5)
        
        self.text_input = scrolledtext.ScrolledText(parent, height=6, width=60, 
                                                  font=('Arial', 11), bg='white', fg='black')
        self.text_input.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)
        
        # Hybrid encryption option
        crypto_frame = tk.Frame(parent, bg='white')
        crypto_frame.pack(fill=tk.X, padx=20, pady=5)
        self.use_hybrid_crypto_var = tk.BooleanVar(value=False)
        tk.Checkbutton(crypto_frame, text="🔐 Use Hybrid Cryptography (AES+RSA)", 
                      variable=self.use_hybrid_crypto_var,
                      font=('Arial', 10, 'bold'), bg='white', fg='black',
                      activebackground='white', activeforeground='black',
                      selectcolor='lightgreen').pack(side=tk.LEFT)
        
        # Info about block encryption for images
        crypto_info = tk.Label(crypto_frame, 
                              text="",
                              font=('Arial', 8, 'italic'), bg='white', fg='gray')
        crypto_info.pack(side=tk.LEFT, padx=10)
        tk.Button(crypto_frame, text="Manage RSA Keys", bg='purple', fg='white',
                 font=('Arial', 9), command=self.manage_rsa_keys).pack(side=tk.LEFT, padx=10)
        
        btn_frame = tk.Frame(parent, bg='white')
        btn_frame.pack(fill=tk.X, padx=20, pady=10)
        
        tk.Button(btn_frame, text="Generate Barcode", bg='green', fg='white', 
                 font=('Arial', 11, 'bold'), command=self.encode_text).pack(side=tk.LEFT, padx=5)
        
        tk.Button(btn_frame, text="Save Barcode", bg='blue', fg='white', 
                 font=('Arial', 11, 'bold'), command=self.save_barcode).pack(side=tk.LEFT, padx=5)
        
        tk.Button(btn_frame, text="Clear", bg='orange', fg='white', 
                 font=('Arial', 11, 'bold'), command=self.clear_encode).pack(side=tk.LEFT, padx=5)
        
        self.encode_status = tk.Label(parent, text="Ready to encode", 
                                     font=('Arial', 10), bg='white', fg='black')
        self.encode_status.pack(anchor='w', padx=20, pady=5)
        
        tk.Label(parent, text="Barcode Preview:", 
                font=('Arial', 12, 'bold'), bg='white', fg='black').pack(anchor='w', padx=20, pady=(20,5))
        
        self.preview_frame = tk.Frame(parent, bg='lightgray', relief='sunken', bd=2)
        self.preview_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)
    
    def setup_decode(self, parent):
        tk.Label(parent, text="Select barcode image:", 
                font=('Arial', 12, 'bold'), bg='white', fg='black').pack(anchor='w', padx=20, pady=(20,5))
        
        file_frame = tk.Frame(parent, bg='white')
        file_frame.pack(fill=tk.X, padx=20, pady=5)
        
        self.file_path_var = tk.StringVar()
        file_entry = tk.Entry(file_frame, textvariable=self.file_path_var, 
                            state='readonly', font=('Arial', 10), bg='white', fg='black')
        file_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0,10))
        
        tk.Button(file_frame, text="Browse", bg='blue', fg='white', 
                 font=('Arial', 10, 'bold'), command=self.browse_file).pack(side=tk.RIGHT)
        
        decode_btn_frame = tk.Frame(parent, bg='white')
        decode_btn_frame.pack(pady=20)
        
        tk.Button(decode_btn_frame, text="Decode Barcode", bg='green', fg='white', 
                 font=('Arial', 12, 'bold'), command=self.decode_barcode).pack(side=tk.LEFT, padx=5)
        
        tk.Button(decode_btn_frame, text="💾 Save Barcode Image", bg='orange', fg='white', 
                 font=('Arial', 12, 'bold'), command=self.save_decoded_barcode_image).pack(side=tk.LEFT, padx=5)
        
        tk.Button(decode_btn_frame, text="🖼️ Save Original Image", bg='purple', fg='white', 
                 font=('Arial', 12, 'bold'), command=self.save_decoded_original_image).pack(side=tk.LEFT, padx=5)
        
        tk.Label(parent, text="Decoded text:", 
                font=('Arial', 12, 'bold'), bg='white', fg='black').pack(anchor='w', padx=20, pady=(20,5))
        
        self.decoded_text = scrolledtext.ScrolledText(parent, height=8, width=60, 
                                                    state=tk.DISABLED, font=('Arial', 11), 
                                                    bg='white', fg='black')
        self.decoded_text.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)
        
        self.decode_status = tk.Label(parent, text="Select a barcode image", 
                                     font=('Arial', 10), bg='white', fg='black')
        self.decode_status.pack(anchor='w', padx=20, pady=5)
    
    def setup_stego(self, parent):
        tk.Label(parent, text="Enter text to hide:", 
                font=('Arial', 12, 'bold'), bg='white', fg='black').pack(anchor='w', padx=20, pady=(20,5))
        
        self.stego_text_input = scrolledtext.ScrolledText(parent, height=4, width=60, 
                                                         font=('Arial', 11), bg='white', fg='black')
        self.stego_text_input.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)
        
        tk.Label(parent, text="Select cover image:", 
                font=('Arial', 12, 'bold'), bg='white', fg='black').pack(anchor='w', padx=20, pady=(20,5))
        
        cover_frame = tk.Frame(parent, bg='white')
        cover_frame.pack(fill=tk.X, padx=20, pady=5)
        
        self.cover_path_var = tk.StringVar()
        cover_entry = tk.Entry(cover_frame, textvariable=self.cover_path_var, 
                             state='readonly', font=('Arial', 10), bg='white', fg='black')
        cover_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0,10))
        
        tk.Button(cover_frame, text="Browse", bg='blue', fg='white', 
                 font=('Arial', 10, 'bold'), command=self.browse_cover).pack(side=tk.RIGHT)
        
        # Method selection frame
        method_frame = tk.Frame(parent, bg='white')
        method_frame.pack(fill=tk.X, padx=20, pady=10)
        
        tk.Label(method_frame, text="Quality Method:", 
                font=('Arial', 11, 'bold'), bg='white', fg='black').pack(side=tk.LEFT, padx=(0,10))
        
        self.method_var = tk.StringVar(value="LSB")
        tk.Radiobutton(method_frame, text="LSB", variable=self.method_var, value="LSB",
                      font=('Arial', 10), bg='white', fg='black', activebackground='white',
                      activeforeground='black').pack(side=tk.LEFT, padx=5)
        tk.Radiobutton(method_frame, text="DCT", variable=self.method_var, value="DCT",
                      font=('Arial', 10), bg='white', fg='black', activebackground='white',
                      activeforeground='black').pack(side=tk.LEFT, padx=5)
        tk.Radiobutton(method_frame, text="Hybrid (LSB+DCT)", variable=self.method_var, value="Hybrid",
                      font=('Arial', 10, 'bold'), bg='white', fg='purple', activebackground='white',
                      activeforeground='purple').pack(side=tk.LEFT, padx=5)
        
        btn_frame = tk.Frame(parent, bg='white')
        btn_frame.pack(fill=tk.X, padx=20, pady=20)
        
        tk.Button(btn_frame, text="Hide Text Directly", bg='green', fg='white', 
                 font=('Arial', 10, 'bold'), command=self.hide_text).pack(side=tk.LEFT, padx=5)
        
        tk.Button(btn_frame, text="Hide as Barcode", bg='blue', fg='white', 
                 font=('Arial', 10, 'bold'), command=self.hide_barcode).pack(side=tk.LEFT, padx=5)
        
        tk.Button(btn_frame, text="Clear", bg='orange', fg='white', 
                 font=('Arial', 10, 'bold'), command=self.clear_stego).pack(side=tk.LEFT, padx=5)
        
        self.stego_status = tk.Label(parent, text="Select a cover image", 
                                    font=('Arial', 10), bg='white', fg='black')
        self.stego_status.pack(anchor='w', padx=20, pady=5)
        
        # Quality metrics display frame
        metrics_frame = tk.Frame(parent, bg='lightblue', relief='raised', bd=2)
        metrics_frame.pack(fill=tk.X, padx=20, pady=10)
        
        tk.Label(metrics_frame, text="Image Quality Metrics", 
                font=('Arial', 12, 'bold'), bg='lightblue', fg='black').pack(pady=5)
        
        metrics_inner = tk.Frame(metrics_frame, bg='lightblue')
        metrics_inner.pack(padx=10, pady=5)
        
        self.psnr_label = tk.Label(metrics_inner, text="PSNR: N/A", 
                                   font=('Arial', 10), bg='lightblue', fg='black')
        self.psnr_label.pack(anchor='w', padx=10, pady=2)
        
        self.ssim_label = tk.Label(metrics_inner, text="SSIM: N/A", 
                                  font=('Arial', 10), bg='lightblue', fg='black')
        self.ssim_label.pack(anchor='w', padx=10, pady=2)
        
        self.ber_label = tk.Label(metrics_inner, text="BER: N/A", 
                                  font=('Arial', 10), bg='lightblue', fg='black')
        self.ber_label.pack(anchor='w', padx=10, pady=2)
    
    def setup_hide_barcode(self, parent):
        # Create scrollable frame with canvas and scrollbar
        canvas = tk.Canvas(parent, bg='white', highlightthickness=0)
        scrollbar = tk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg='white')
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Update canvas width when scrollable_frame changes
        def configure_scroll_region(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
            # Update canvas window width to match canvas
            canvas_width = event.width
            canvas.itemconfig(canvas.find_all()[0], width=canvas_width)
        
        scrollable_frame.bind("<Configure>", configure_scroll_region)
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(canvas.find_all()[0], width=e.width))
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Bind mousewheel to canvas
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        
        # Use scrollable_frame as the parent for all content
        content_parent = scrollable_frame
        
        tk.Label(content_parent, text="Select barcode file to hide:", 
                font=('Arial', 12, 'bold'), bg='white', fg='black').pack(anchor='w', padx=20, pady=(20,5))
        
        barcode_frame = tk.Frame(content_parent, bg='white')
        barcode_frame.pack(fill=tk.X, padx=20, pady=5)
        
        self.barcode_file_var = tk.StringVar()
        barcode_entry = tk.Entry(barcode_frame, textvariable=self.barcode_file_var, 
                               state='readonly', font=('Arial', 10), bg='white', fg='black')
        barcode_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0,10))
        
        tk.Button(barcode_frame, text="Browse Barcode", bg='blue', fg='white', 
                 font=('Arial', 10, 'bold'), command=self.browse_barcode_file).pack(side=tk.RIGHT)
        
        tk.Label(content_parent, text="Select cover image:", 
                font=('Arial', 12, 'bold'), bg='white', fg='black').pack(anchor='w', padx=20, pady=(20,5))
        
        cover_frame = tk.Frame(content_parent, bg='white')
        cover_frame.pack(fill=tk.X, padx=20, pady=5)
        
        self.cover_path_var2 = tk.StringVar()
        cover_entry = tk.Entry(cover_frame, textvariable=self.cover_path_var2, 
                              state='readonly', font=('Arial', 10), bg='white', fg='black')
        cover_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0,10))
        
        tk.Button(cover_frame, text="Browse Cover", bg='blue', fg='white', 
                 font=('Arial', 10, 'bold'), command=self.browse_cover2).pack(side=tk.RIGHT)
        
        # Image preview frames - Create first for reference
        preview_container = tk.Frame(content_parent, bg='white')
        
        # Now pack preview container
        preview_container.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # Cover image preview section
        cover_preview_section = tk.Frame(preview_container, bg='white')
        cover_preview_section.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0,10))
        
        cover_preview_label = tk.Label(cover_preview_section, text="Cover Image Preview:", 
                                      font=('Arial', 11, 'bold'), bg='white', fg='black')
        cover_preview_label.pack(anchor='w', pady=(0,5))
        
        self.hide_barcode_cover_preview_frame = tk.Frame(cover_preview_section, bg='lightgray', 
                                                        relief='sunken', bd=2)
        self.hide_barcode_cover_preview_frame.pack(fill=tk.BOTH, expand=True)
        
        # Add placeholder text for cover image
        cover_placeholder = tk.Label(self.hide_barcode_cover_preview_frame, 
                                    text="Cover image will appear here\nafter selecting cover image", 
                                    bg='lightgray', fg='gray', font=('Arial', 10))
        cover_placeholder.pack(expand=True)
        
        # Stego image preview section
        stego_preview_section = tk.Frame(preview_container, bg='white')
        stego_preview_section.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10,0))
        
        stego_preview_label = tk.Label(stego_preview_section, text="Stego Image Preview:", 
                                      font=('Arial', 11, 'bold'), bg='white', fg='black')
        stego_preview_label.pack(anchor='w', pady=(0,5))
        
        self.hide_barcode_stego_preview_frame = tk.Frame(stego_preview_section, bg='lightgray', 
                                                         relief='sunken', bd=2)
        self.hide_barcode_stego_preview_frame.pack(fill=tk.BOTH, expand=True)
        
        # Add placeholder text
        placeholder = tk.Label(self.hide_barcode_stego_preview_frame, 
                               text="Stego image will appear here\nafter hiding barcode", 
                               bg='lightgray', fg='gray', font=('Arial', 10))
        placeholder.pack(expand=True)
        
        # Quality method selection frame
        quality_method_frame = tk.Frame(content_parent, bg='white')
        quality_method_frame.pack(fill=tk.X, padx=20, pady=10)
        
        tk.Label(quality_method_frame, text="Quality Method:", 
                font=('Arial', 11, 'bold'), bg='white', fg='black').pack(side=tk.LEFT, padx=(0,10))
        
        self.hide_barcode_method_var = tk.StringVar(value="LSB")
        tk.Radiobutton(quality_method_frame, text="LSB", variable=self.hide_barcode_method_var, value="LSB",
                      font=('Arial', 10), bg='white', fg='black', activebackground='white',
                      activeforeground='black').pack(side=tk.LEFT, padx=5)
        tk.Radiobutton(quality_method_frame, text="DCT", variable=self.hide_barcode_method_var, value="DCT",
                      font=('Arial', 10), bg='white', fg='black', activebackground='white',
                      activeforeground='black').pack(side=tk.LEFT, padx=5)
        tk.Radiobutton(quality_method_frame, text="Hybrid (LSB+DCT)", variable=self.hide_barcode_method_var, value="Hybrid",
                      font=('Arial', 10, 'bold'), bg='white', fg='purple', activebackground='white',
                      activeforeground='purple').pack(side=tk.LEFT, padx=5)
        
        # JPEG-robust mode checkbox (for DCT method)
        jpeg_robust_frame = tk.Frame(content_parent, bg='white')
        jpeg_robust_frame.pack(fill=tk.X, padx=20, pady=5)
        
        self.jpeg_robust_var = tk.BooleanVar(value=False)
        jpeg_checkbox = tk.Checkbutton(jpeg_robust_frame, 
                                      text="🔒 JPEG-Robust Mode (survives WhatsApp/compression)", 
                                      variable=self.jpeg_robust_var,
                                      font=('Arial', 9), bg='white', fg='darkgreen',
                                      activebackground='white', activeforeground='darkgreen')
        jpeg_checkbox.pack(side=tk.LEFT)
        
        # Info label
        info_label = tk.Label(jpeg_robust_frame, 
                             text="(Lower capacity, but survives JPEG compression)",
                             font=('Arial', 8), bg='white', fg='gray')
        info_label.pack(side=tk.LEFT, padx=10)
        
        tk.Button(content_parent, text="Hide Barcode File in Cover Image", bg='purple', fg='white', 
                 font=('Arial', 12, 'bold'), command=self.hide_barcode_file).pack(pady=20)
        
        self.hide_barcode_status = tk.Label(content_parent, text="Select a barcode file and cover image", 
                                           font=('Arial', 10), bg='white', fg='black')
        self.hide_barcode_status.pack(anchor='w', padx=20, pady=5)
        
        # Quality metrics and comparison display frame (combined)
        hide_barcode_metrics_frame = tk.Frame(content_parent, bg='lightblue', relief='raised', bd=2)
        hide_barcode_metrics_frame.pack(fill=tk.X, padx=20, pady=10)
        
        # Title row
        title_row = tk.Frame(hide_barcode_metrics_frame, bg='lightblue')
        title_row.pack(fill=tk.X, pady=5)
        
        tk.Label(title_row, text="Image Quality Metrics", 
                font=('Arial', 12, 'bold'), bg='lightblue', fg='black').pack(side=tk.LEFT, padx=10)
        
        tk.Label(title_row, text="📊 Image Comparison", 
                font=('Arial', 12, 'bold'), bg='lightblue', fg='black').pack(side=tk.RIGHT, padx=10)
        
        # Content row with two columns
        content_row = tk.Frame(hide_barcode_metrics_frame, bg='lightblue')
        content_row.pack(fill=tk.X, padx=10, pady=5)
        
        # Left column: Quality Metrics
        metrics_column = tk.Frame(content_row, bg='lightblue')
        metrics_column.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        
        self.hide_barcode_psnr_label = tk.Label(metrics_column, text="PSNR: N/A", 
                                               font=('Arial', 10), bg='lightblue', fg='black')
        self.hide_barcode_psnr_label.pack(anchor='w', padx=10, pady=2)
        
        self.hide_barcode_ssim_label = tk.Label(metrics_column, text="SSIM: N/A", 
                                                font=('Arial', 10), bg='lightblue', fg='black')
        self.hide_barcode_ssim_label.pack(anchor='w', padx=10, pady=2)
        
        self.hide_barcode_ber_label = tk.Label(metrics_column, text="BER: N/A", 
                                                font=('Arial', 10), bg='lightblue', fg='black')
        self.hide_barcode_ber_label.pack(anchor='w', padx=10, pady=2)
        
        # Vertical separator
        separator = tk.Frame(content_row, bg='darkblue', width=2)
        separator.pack(side=tk.LEFT, fill=tk.Y, padx=10)
        
        # Right column: Image Comparison (compact layout)
        comparison_column = tk.Frame(content_row, bg='lightblue')
        comparison_column.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        
        # Cover and Stego side by side to save vertical space
        images_row = tk.Frame(comparison_column, bg='lightblue')
        images_row.pack(fill=tk.X, pady=1)
        
        # Cover image info (left)
        cover_info_frame = tk.Frame(images_row, bg='lightblue')
        cover_info_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2)
        
        tk.Label(cover_info_frame, text="🖼️ Cover", 
                font=('Arial', 8, 'bold'), bg='lightblue', fg='darkblue').pack(anchor='w', pady=(0,0))
        
        self.hide_barcode_cover_dimensions_label = tk.Label(cover_info_frame, text="Size: N/A", 
                                                           font=('Arial', 8), bg='lightblue', fg='black')
        self.hide_barcode_cover_dimensions_label.pack(anchor='w', padx=2, pady=0)
        
        self.hide_barcode_cover_size_label = tk.Label(cover_info_frame, text="File: N/A", 
                                                      font=('Arial', 8), bg='lightblue', fg='black')
        self.hide_barcode_cover_size_label.pack(anchor='w', padx=2, pady=0)
        
        self.hide_barcode_cover_pixels_label = tk.Label(cover_info_frame, text="Pixels: N/A", 
                                                        font=('Arial', 8), bg='lightblue', fg='black')
        self.hide_barcode_cover_pixels_label.pack(anchor='w', padx=2, pady=0)
        
        # Small separator between Cover and Stego
        mini_sep = tk.Frame(images_row, bg='gray', width=1)
        mini_sep.pack(side=tk.LEFT, fill=tk.Y, padx=3)
        
        # Stego image info (right)
        stego_info_frame = tk.Frame(images_row, bg='lightblue')
        stego_info_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2)
        
        tk.Label(stego_info_frame, text="🔒 Stego", 
                font=('Arial', 8, 'bold'), bg='lightblue', fg='darkgreen').pack(anchor='w', pady=(0,0))
        
        self.hide_barcode_stego_dimensions_label = tk.Label(stego_info_frame, text="Size: N/A", 
                                                            font=('Arial', 8), bg='lightblue', fg='black')
        self.hide_barcode_stego_dimensions_label.pack(anchor='w', padx=2, pady=0)
        
        self.hide_barcode_stego_size_label = tk.Label(stego_info_frame, text="File: N/A", 
                                                      font=('Arial', 8), bg='lightblue', fg='black')
        self.hide_barcode_stego_size_label.pack(anchor='w', padx=2, pady=0)
        
        self.hide_barcode_stego_pixels_label = tk.Label(stego_info_frame, text="Pixels: N/A", 
                                                        font=('Arial', 8), bg='lightblue', fg='black')
        self.hide_barcode_stego_pixels_label.pack(anchor='w', padx=2, pady=0)
        
        # Advanced Analysis Section - Move here for better visibility
        advanced_frame = tk.Frame(comparison_column, bg='lightblue', relief='solid', bd=1)
        advanced_frame.pack(fill=tk.X, pady=(3,2))
        
        tk.Label(advanced_frame, text="🔬 Advanced Analysis", 
                font=('Arial', 8, 'bold'), bg='lightblue', fg='purple').pack(pady=(2,1))
        
        # Compact grid layout for all advanced metrics
        advanced_grid = tk.Frame(advanced_frame, bg='lightblue')
        advanced_grid.pack(fill=tk.X, padx=3, pady=1)
        
        # Row 1: Entropy (compact)
        entropy_compact = tk.Frame(advanced_grid, bg='lightblue')
        entropy_compact.pack(fill=tk.X, pady=1)
        
        self.hide_barcode_entropy_cover_label = tk.Label(entropy_compact, text="Entropy C: N/A", 
                                                         font=('Arial', 7), bg='lightblue', fg='darkblue')
        self.hide_barcode_entropy_cover_label.pack(side=tk.LEFT, padx=2)
        
        self.hide_barcode_entropy_stego_label = tk.Label(entropy_compact, text="S: N/A", 
                                                         font=('Arial', 7), bg='lightblue', fg='darkgreen')
        self.hide_barcode_entropy_stego_label.pack(side=tk.LEFT, padx=2)
        
        # Row 2: Embedded size and LSB test (compact)
        detection_compact = tk.Frame(advanced_grid, bg='lightblue')
        detection_compact.pack(fill=tk.X, pady=1)
        
        self.hide_barcode_embedded_size_label = tk.Label(detection_compact, text="Embedded: N/A", 
                                                         font=('Arial', 7), bg='lightblue', fg='orange')
        self.hide_barcode_embedded_size_label.pack(side=tk.LEFT, padx=2)
        
        self.hide_barcode_chi_square_label = tk.Label(detection_compact, text="LSB: N/A", 
                                                      font=('Arial', 7), bg='lightblue', fg='darkred')
        self.hide_barcode_chi_square_label.pack(side=tk.LEFT, padx=2)
        
        # Row 3: Histogram variance (compact)
        hist_compact = tk.Frame(advanced_grid, bg='lightblue')
        hist_compact.pack(fill=tk.X, pady=1)
        
        self.hide_barcode_hist_variance_label = tk.Label(hist_compact, text="Hist Var: N/A", 
                                                          font=('Arial', 7), bg='lightblue', fg='darkmagenta')
        self.hide_barcode_hist_variance_label.pack(side=tk.LEFT, padx=2)
        
        # Differences section (compact) - After Advanced Analysis
        difference_frame = tk.Frame(comparison_column, bg='lightblue')
        difference_frame.pack(fill=tk.X, pady=(2,0))
        
        tk.Label(difference_frame, text="📏 Differences:", 
                font=('Arial', 8, 'bold'), bg='lightblue', fg='darkred').pack(anchor='w', pady=(0,0))
        
        diff_inner = tk.Frame(difference_frame, bg='lightblue')
        diff_inner.pack(fill=tk.X, pady=0)
        
        self.hide_barcode_size_diff_label = tk.Label(diff_inner, text="Size: N/A", 
                                                     font=('Arial', 8), bg='lightblue', fg='darkred')
        self.hide_barcode_size_diff_label.pack(side=tk.LEFT, padx=3, pady=0)
        
        self.hide_barcode_dimension_diff_label = tk.Label(diff_inner, text="Dim: N/A", 
                                                          font=('Arial', 8), bg='lightblue', fg='darkred')
        self.hide_barcode_dimension_diff_label.pack(side=tk.LEFT, padx=3, pady=0)
        
        self.hide_barcode_pixel_diff_label = tk.Label(diff_inner, text="Pixels: N/A", 
                                                      font=('Arial', 8), bg='lightblue', fg='darkred')
        self.hide_barcode_pixel_diff_label.pack(side=tk.LEFT, padx=3, pady=0)
    
    def setup_extract_stego(self, parent):
        tk.Label(parent, text="Select stego image to extract from:", 
                font=('Arial', 12, 'bold'), bg='white', fg='black').pack(anchor='w', padx=20, pady=(20,5))
        
        stego_frame = tk.Frame(parent, bg='white')
        stego_frame.pack(fill=tk.X, padx=20, pady=5)
        
        self.stego_path_var = tk.StringVar()
        stego_entry = tk.Entry(stego_frame, textvariable=self.stego_path_var, 
                              state='readonly', font=('Arial', 10), bg='white', fg='black')
        stego_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0,10))
        
        tk.Button(stego_frame, text="Browse Stego", bg='blue', fg='white', 
                 font=('Arial', 10, 'bold'), command=self.browse_stego).pack(side=tk.RIGHT)
        
        # Method selection for extraction
        extract_method_frame = tk.Frame(parent, bg='white')
        extract_method_frame.pack(fill=tk.X, padx=20, pady=10)
        
        tk.Label(extract_method_frame, text="Quality Method:", 
                font=('Arial', 11, 'bold'), bg='white', fg='black').pack(side=tk.LEFT, padx=(0,10))
        
        self.extract_method_var = tk.StringVar(value="LSB")
        tk.Radiobutton(extract_method_frame, text="LSB", variable=self.extract_method_var, value="LSB",
                      font=('Arial', 10), bg='white', fg='black', activebackground='white',
                      activeforeground='black').pack(side=tk.LEFT, padx=5)
        tk.Radiobutton(extract_method_frame, text="DCT", variable=self.extract_method_var, value="DCT",
                      font=('Arial', 10), bg='white', fg='black', activebackground='white',
                      activeforeground='black').pack(side=tk.LEFT, padx=5)
        tk.Radiobutton(extract_method_frame, text="Hybrid (LSB+DCT)", variable=self.extract_method_var, value="Hybrid",
                      font=('Arial', 10, 'bold'), bg='white', fg='purple', activebackground='white',
                      activeforeground='purple').pack(side=tk.LEFT, padx=5)
        
        btn_frame = tk.Frame(parent, bg='white')
        btn_frame.pack(fill=tk.X, padx=20, pady=20)
        
        tk.Button(btn_frame, text="🔧 Fix Noise", bg='purple', fg='white', 
                 font=('Arial', 10, 'bold'), command=self.fix_noise_dialog).pack(side=tk.LEFT, padx=5)
        
        tk.Button(btn_frame, text="🤖 Auto-Denoise & Extract", bg='darkgreen', fg='white', 
                 font=('Arial', 10, 'bold'), command=self.auto_denoise_and_extract).pack(side=tk.LEFT, padx=5)
        
        tk.Button(btn_frame, text="Extract Text Directly", bg='green', fg='white', 
                 font=('Arial', 10, 'bold'), command=self.extract_text).pack(side=tk.LEFT, padx=5)
        
        tk.Button(btn_frame, text="Extract Barcode", bg='blue', fg='white', 
                 font=('Arial', 10, 'bold'), command=self.extract_barcode).pack(side=tk.LEFT, padx=5)
        
        tk.Button(btn_frame, text="💾 Save Extracted Barcode Image", bg='orange', fg='white', 
                 font=('Arial', 10, 'bold'), command=self.save_extracted_barcode_image).pack(side=tk.LEFT, padx=5)
        
        tk.Label(parent, text="Extracted text:", 
                font=('Arial', 12, 'bold'), bg='white', fg='black').pack(anchor='w', padx=20, pady=(20,5))
        
        self.extracted_text = scrolledtext.ScrolledText(parent, height=8, width=60, 
                                                      state=tk.DISABLED, font=('Arial', 11), 
                                                      bg='white', fg='black')
        self.extracted_text.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)
        
        self.extract_status = tk.Label(parent, text="Select a stego image", 
                                      font=('Arial', 10), bg='white', fg='black')
        self.extract_status.pack(anchor='w', padx=20, pady=5)
    
    def setup_diagnostic(self, parent):
        tk.Label(parent, text="Diagnostic Tool", 
                font=('Arial', 16, 'bold'), bg='white', fg='black').pack(pady=10)
        
        tk.Label(parent, text="Use this tool if extraction fails to analyze the image.", 
                font=('Arial', 10), bg='white', fg='gray').pack(pady=5)
        
        file_frame = tk.Frame(parent, bg='white')
        file_frame.pack(fill=tk.X, padx=20, pady=10)
        
        self.diag_path_var = tk.StringVar()
        tk.Entry(file_frame, textvariable=self.diag_path_var, 
                state='readonly', font=('Arial', 10), bg='white', fg='black').pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0,10))
        
        tk.Button(file_frame, text="Browse Image", bg='blue', fg='white', 
                 command=self.browse_diagnostic).pack(side=tk.RIGHT)
        
        tk.Button(parent, text="Run Diagnostics", bg='purple', fg='white', 
                 font=('Arial', 12, 'bold'), command=self.run_diagnostic).pack(pady=10)
        
        self.diag_output = scrolledtext.ScrolledText(parent, height=20, width=80, 
                                                   font=('Consolas', 10), bg='black', fg='lightgreen')
        self.diag_output.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
    
    def browse_file(self):
        filename = filedialog.askopenfilename(filetypes=[("Image files", "*.png *.bmp *.jpg *.jpeg *.tiff")])
        if filename:
            self.file_path_var.set(filename)
            self.decode_status.config(text=f"Selected: {os.path.basename(filename)}")
    
    def browse_cover(self):
        filename = filedialog.askopenfilename(filetypes=[("Image files", "*.png *.bmp *.jpg *.jpeg *.tiff")])
        if filename:
            self.cover_path_var.set(filename)
            self.current_cover_path = filename  # Store for metrics
            self.stego_status.config(text=f"Selected: {os.path.basename(filename)}")
            # Reset metrics
            self.psnr_label.config(text="PSNR: N/A")
            self.ssim_label.config(text="SSIM: N/A")
            self.ber_label.config(text="BER: N/A")
    
    def browse_cover2(self):
        filename = filedialog.askopenfilename(filetypes=[("Image files", "*.png *.bmp *.jpg *.jpeg *.tiff")])
        if filename:
            self.cover_path_var2.set(filename)
            self.current_cover_path2 = filename  # Store for metrics
            self.hide_barcode_status.config(text=f"Selected: {os.path.basename(filename)}")
            # Reset metrics
            self.hide_barcode_psnr_label.config(text="PSNR: N/A")
            self.hide_barcode_ssim_label.config(text="SSIM: N/A")
            self.hide_barcode_ber_label.config(text="BER: N/A")
            # Display cover image preview
            self.show_cover_image_preview(filename)
            # Update comparison with cover image info (stego will be N/A)
            self.update_image_comparison(filename, None)
            # Clear stego preview when new cover is selected
            if self.hide_barcode_stego_preview_frame:
                for widget in self.hide_barcode_stego_preview_frame.winfo_children():
                    widget.destroy()
                placeholder = tk.Label(self.hide_barcode_stego_preview_frame, 
                                    text="Stego image will appear here\nafter hiding barcode", 
                                    bg='lightgray', fg='gray', font=('Arial', 10))
                placeholder.pack(expand=True)
    
    def browse_stego(self):
        filename = filedialog.askopenfilename(filetypes=[("Image files", "*.png *.bmp *.tiff")])
        if filename:
            self.stego_path_var.set(filename)
            self.extract_status.config(text=f"Selected: {os.path.basename(filename)}")
            self.denoised_image_path = None  # Reset denoised image when new image is selected
    
    def browse_barcode_file(self):
        filename = filedialog.askopenfilename(filetypes=[("Image files", "*.png *.bmp")])
        if filename:
            self.barcode_file_var.set(filename)
            self.hide_barcode_status.config(text=f"Selected barcode: {os.path.basename(filename)}")
    
    def browse_diagnostic(self):
        filename = filedialog.askopenfilename(filetypes=[("Image files", "*.png *.bmp *.tiff *.jpg *.jpeg")])
        if filename:
            self.diag_path_var.set(filename)
    
    def _format_elapsed(self, seconds):
        """Format elapsed seconds for user-facing timing output."""
        return f"{seconds:.3f}s"
    
    def _build_timing_text(self, timings):
        """
        Build multi-line timing details.
        timings: list of (label, seconds)
        """
        lines = []
        for label, seconds in timings:
            if seconds is None:
                continue
            lines.append(f"{label}: {self._format_elapsed(seconds)}")
        return "\n".join(lines)
    
    def _write_extract_output(self, content, timing_text):
        """Write extraction output and timing details in Extract tab."""
        self.extracted_text.config(state=tk.NORMAL)
        self.extracted_text.delete('1.0', tk.END)
        self.extracted_text.insert('1.0', content)
        if timing_text:
            self.extracted_text.insert(tk.END, f"\n\n--- Timing ---\n{timing_text}")
        self.extracted_text.config(state=tk.DISABLED)
    
    def enter_text(self):
        self.text_input.delete('1.0', tk.END)
        self.text_input.insert('1.0', "Enter your text here...")
    
    def enter_photo(self):
        filename = filedialog.askopenfilename(filetypes=[("Image files", "*.png *.jpg *.jpeg *.bmp *.gif")])
        if filename:
            try:
                # Read image file
                with open(filename, "rb") as image_file:
                    encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                
                # Get image info
                img = Image.open(filename)
                width, height = img.size
                format_name = img.format
                
                # Create formatted string with metadata
                # Format: [IMAGE:filename:format:widthxheight]base64data
                basename = os.path.basename(filename)
                formatted_data = f"[IMAGE:{basename}:{format_name}:{width}x{height}]\n{encoded_string}"
                
                self.text_input.delete('1.0', tk.END)
                self.text_input.insert('1.0', formatted_data)
                
                messagebox.showinfo("Success", f"Image '{basename}' loaded successfully!\nSize: {len(encoded_string):,} bytes")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load image: {str(e)}")
    
    def manage_rsa_keys(self):
        """Show dialog to manage RSA keys"""
        manage_window = tk.Toplevel(self.root)
        manage_window.title("Manage RSA Keys")
        manage_window.geometry("500x400")
        
        tk.Label(manage_window, text="RSA Key Management", 
                font=('Arial', 14, 'bold')).pack(pady=10)
        
        # Key status
        status_frame = tk.Frame(manage_window, relief='groove', bd=2)
        status_frame.pack(fill=tk.X, padx=20, pady=10)
        
        has_keys = self.cbs.hybrid_crypto is not None
        status_text = "✅ Keys Loaded" if has_keys else "❌ No Keys Found"
        status_color = "green" if has_keys else "red"
        
        tk.Label(status_frame, text=f"Status: {status_text}", 
                fg=status_color, font=('Arial', 11, 'bold')).pack(pady=10)
        
        if has_keys:
            # Show public key fingerprint (hash)
            pub_pem = self.cbs.hybrid_crypto.get_public_key_pem().encode()
            fingerprint = hashlib.sha256(pub_pem).hexdigest()[:16]
            tk.Label(status_frame, text=f"Key Fingerprint: {fingerprint}...", 
                    font=('Arial', 9)).pack(pady=5)
        
        # Actions
        btn_frame = tk.Frame(manage_window)
        btn_frame.pack(pady=20)
        
        def generate_new():
            if messagebox.askyesno("Confirm", "Generate new keys? This will overwrite existing keys!"):
                try:
                    self.cbs.hybrid_crypto = HybridCrypto()
                    self.cbs.hybrid_crypto.save_rsa_keys()
                    messagebox.showinfo("Success", "New RSA keys generated and saved!")
                    manage_window.destroy()
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to generate keys: {e}")
        
        def export_public():
            if not self.cbs.hybrid_crypto:
                messagebox.showerror("Error", "No keys available")
                return
            
            filename = filedialog.asksaveasfilename(
                defaultextension=".pem",
                filetypes=[("PEM files", "*.pem")],
                initialfile="public_key.pem"
            )
            if filename:
                try:
                    with open(filename, 'wb') as f:
                        f.write(self.cbs.hybrid_crypto.get_public_key_pem().encode())
                    messagebox.showinfo("Success", f"Public key exported to {filename}")
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to export: {e}")
        
        def import_keys():
            private_path = filedialog.askopenfilename(title="Select Private Key", filetypes=[("PEM files", "*.pem")])
            if not private_path: return
            
            public_path = filedialog.askopenfilename(title="Select Public Key", filetypes=[("PEM files", "*.pem")])
            if not public_path: return
            
            try:
                priv, pub = HybridCrypto.load_rsa_keys(private_path, public_path)
                self.cbs.hybrid_crypto = HybridCrypto(pub, priv)
                # Save to default location
                self.cbs.hybrid_crypto.save_rsa_keys()
                messagebox.showinfo("Success", "Keys imported successfully!")
                manage_window.destroy()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to import keys: {e}")
        
        tk.Button(btn_frame, text="Generate New Keys", bg='red', fg='white',
                 command=generate_new).pack(fill=tk.X, pady=5)
        
        tk.Button(btn_frame, text="Export Public Key", bg='blue', fg='white',
                 command=export_public).pack(fill=tk.X, pady=5)
        
        tk.Button(btn_frame, text="Import Keys", bg='green', fg='white',
                 command=import_keys).pack(fill=tk.X, pady=5)
    
    def encode_text(self):
        text = self.text_input.get('1.0', tk.END).strip()
        if not text:
            messagebox.showwarning("Warning", "Please enter some text first!")
            return
        
        try:
            op_start = time.perf_counter()
            # Check if hybrid encryption is requested
            use_hybrid = self.use_hybrid_crypto_var.get()
            
            # Generate barcode pattern
            encode_start = time.perf_counter()
            self.current_pattern = self.cbs.encode(text, use_hybrid_encryption=use_hybrid)
            encode_time = time.perf_counter() - encode_start
            
            # Show preview
            preview_start = time.perf_counter()
            self.show_preview(self.current_pattern)
            preview_time = time.perf_counter() - preview_start
            total_time = time.perf_counter() - op_start
            
            # Update status
            info = f"Generated {self.current_pattern.shape[1]}x{self.current_pattern.shape[0]} barcode"
            if use_hybrid:
                info += " (Hybrid Encrypted)"
            info += f" | Total: {self._format_elapsed(total_time)}"
            self.encode_status.config(text=info, fg='green')
            
            timing_text = self._build_timing_text([
                ("Encode time", encode_time),
                ("Preview render", preview_time),
                ("Total", total_time),
            ])
            messagebox.showinfo("Success", f"Barcode generated successfully!\n\n{timing_text}")
            
        except Exception as e:
            messagebox.showerror("Error", str(e))
            self.encode_status.config(text="Error generating barcode", fg='red')
    
    def show_preview(self, pattern):
        # Clear previous preview
        for widget in self.preview_frame.winfo_children():
            widget.destroy()
        
        # Create image from pattern
        height, width = pattern.shape
        
        # Scale up for visibility (max 300x300 preview)
        scale = min(300 // width, 300 // height, 10)
        scale = max(1, scale)
        
        scaled_pattern = np.repeat(np.repeat(pattern, scale, axis=0), scale, axis=1)
        scaled_pattern = scaled_pattern * 85
        scaled_pattern = np.clip(scaled_pattern, 0, 255).astype(np.uint8)
        
        img = Image.fromarray(scaled_pattern, mode='L')
        photo = ImageTk.PhotoImage(img)
        
        label = tk.Label(self.preview_frame, image=photo, bg='lightgray')
        label.image = photo  # Keep reference
        label.pack(expand=True)
    
    def save_barcode(self):
        if self.current_pattern is None:
            messagebox.showwarning("Warning", "Please generate a barcode first!")
            return
        
        filename = filedialog.asksaveasfilename(defaultextension=".png",
                                              filetypes=[("PNG files", "*.png")])
        if filename:
            try:
                self.cbs.save_barcode(self.current_pattern, filename)
                messagebox.showinfo("Success", "Barcode saved successfully!")
            except Exception as e:
                messagebox.showerror("Error", str(e))
    
    def clear_encode(self):
        self.text_input.delete('1.0', tk.END)
        self.current_pattern = None
        for widget in self.preview_frame.winfo_children():
            widget.destroy()
        self.encode_status.config(text="Ready to encode", fg='black')
    
    def decode_barcode(self):
        file_path = self.file_path_var.get()
        if not file_path:
            messagebox.showwarning("Warning", "Please select a barcode image first!")
            return
        
        try:
            op_start = time.perf_counter()
            image_parse_time = None
            
            load_start = time.perf_counter()
            pattern = self.cbs.load_barcode(file_path)
            load_time = time.perf_counter() - load_start
            
            # Try to decode with hybrid decryption enabled
            # The decoder handles both encrypted and non-encrypted data automatically
            decode_start = time.perf_counter()
            text = self.cbs.decode(pattern, use_hybrid_decryption=True)
            decode_time = time.perf_counter() - decode_start
            
            # Check if it's an image
            if text.startswith("[IMAGE:"):
                # Check if it's still encrypted (decryption failed)
                if "[BLOCK_ENC:" in text or "[HYBRID_ENCRYPTED" in text:
                     messagebox.showwarning("Decryption Failed", 
                         "The barcode contains encrypted data that could not be decrypted.\n\n"
                         "This means the barcode was created with DIFFERENT encryption keys.\n\n"
                         "To decrypt this barcode:\n"
                         "1. Find the original private_key.pem and public_key.pem files\n"
                         "2. Use 'Manage RSA Keys' → 'Import Keys' to load them\n\n"
                         "OR create a new barcode without encryption (uncheck the encryption option).")
                     # Fall through to display text
                else:
                    try:
                        parse_start = time.perf_counter()
                        # Parse image data - more robust splitting
                        # Find the end of the header
                        header_end = text.find(']')
                        if header_end != -1:
                            header = text[:header_end+1]
                            encoded_string = text[header_end+1:].strip()
                            
                            # Extract metadata
                            # Header format: [IMAGE:filename:format:widthxheight]
                            meta = header[7:-1].split(':')
                            if len(meta) >= 3:
                                orig_filename = meta[0]
                                img_format = meta[1]
                                
                                # Decode base64
                                try:
                                    # Sanitize: Remove any non-base64 characters
                                    import re
                                    encoded_string = re.sub(r'[^A-Za-z0-9+/=]', '', encoded_string)
                                    
                                    image_data = base64.b64decode(encoded_string)
                                    
                                    # Load image for saving later
                                    self.decoded_image = Image.open(io.BytesIO(image_data))
                                    
                                    # Display info
                                    self.decoded_text.config(state=tk.NORMAL)
                                    self.decoded_text.delete('1.0', tk.END)
                                    self.decoded_text.insert('1.0', f"Decoded Image: {orig_filename}\nFormat: {img_format}\nSize: {len(image_data):,} bytes\n\nClick 'Save Original Image' to save it.")
                                    self.decoded_text.config(state=tk.DISABLED)
                                    
                                    image_parse_time = time.perf_counter() - parse_start
                                    total_time = time.perf_counter() - op_start
                                    self.decode_status.config(
                                        text=f"Image decoded successfully! (Total: {self._format_elapsed(total_time)})",
                                        fg='green'
                                    )
                                    timing_text = self._build_timing_text([
                                        ("Upload/load", load_time),
                                        ("Decode", decode_time),
                                        ("Image parse", image_parse_time),
                                        ("Total", total_time),
                                    ])
                                    messagebox.showinfo("Success", f"Image decoded successfully!\n\n{timing_text}")
                                    return
                                except Exception as e:
                                    print(f"Base64/Image error: {e}")
                                    # If image loading fails, we still show the text
                        else:
                            print("Header end ']' not found")
                    except Exception as e:
                        print(f"Image parsing error: {e}")
                        # Fall through to display as text if parsing fails
            
            self.decoded_text.config(state=tk.NORMAL)
            self.decoded_text.delete('1.0', tk.END)
            self.decoded_text.insert('1.0', text)
            self.decoded_text.config(state=tk.DISABLED)
            total_time = time.perf_counter() - op_start
            self.decode_status.config(text=f"Decoded successfully! (Total: {self._format_elapsed(total_time)})", fg='green')
            timing_text = self._build_timing_text([
                ("Upload/load", load_time),
                ("Decode", decode_time),
                ("Total", total_time),
            ])
            messagebox.showinfo("Success", f"Decoded successfully!\n\n{timing_text}")
            
        except Exception as e:
            messagebox.showerror("Error", str(e))
            self.decode_status.config(text="Error decoding", fg='red')
    
    def save_decoded_original_image(self):
        if self.decoded_image is None:
            # Fallback: Try to parse from the text box content
            try:
                content = self.decoded_text.get("1.0", tk.END).strip()
                if content.startswith("[IMAGE:"):
                    header_end = content.find(']')
                    if header_end != -1:
                        encoded_string = content[header_end+1:].strip()
                        
                        # Sanitize: Remove any non-base64 characters (including non-ASCII)
                        # Keep only A-Z, a-z, 0-9, +, /, =
                        import re
                        encoded_string = re.sub(r'[^A-Za-z0-9+/=]', '', encoded_string)
                        
                        image_data = base64.b64decode(encoded_string)
                        self.decoded_image = Image.open(io.BytesIO(image_data))
                        print("Successfully recovered image from text box")
                    else:
                        raise ValueError("Invalid image format: missing header end")
                else:
                    messagebox.showwarning("Warning", "No image decoded! Decode a barcode containing an image first.")
                    return
            except Exception as e:
                messagebox.showerror("Parsing Error", f"Could not parse image from text: {e}")
                return
        
        filename = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG files", "*.png"), ("JPEG files", "*.jpg"), ("All files", "*.*")],
            title="Save Decoded Image"
        )
        if filename:
            try:
                self.decoded_image.save(filename)
                messagebox.showinfo("Success", f"Image saved to {filename}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save image: {e}")
    
    def save_decoded_barcode_image(self):
        # This function seems redundant if we're decoding FROM a barcode image
        # But maybe the user wants to re-save it?
        # Or maybe this was meant for "Extract from Stego" tab?
        # Let's assume it saves the currently loaded barcode pattern
        file_path = self.file_path_var.get()
        if not file_path:
            messagebox.showwarning("Warning", "No barcode loaded.")
            return
            
        filename = filedialog.asksaveasfilename(defaultextension=".png",
                                              filetypes=[("PNG files", "*.png")])
        if filename:
            try:
                # Just copy the file
                img = Image.open(file_path)
                img.save(filename)
                messagebox.showinfo("Success", "Barcode image saved!")
            except Exception as e:
                messagebox.showerror("Error", str(e))
    
    def hide_text(self):
        text = self.stego_text_input.get('1.0', tk.END).strip()
        cover_path = self.cover_path_var.get()
        
        if not text or not cover_path:
            messagebox.showwarning("Warning", "Please enter text and select a cover image!")
            return
        
        output_path = filedialog.asksaveasfilename(defaultextension=".png",
                                                 filetypes=[("PNG files", "*.png")])
        if output_path:
            try:
                op_start = time.perf_counter()
                method = self.method_var.get()
                
                hide_start = time.perf_counter()
                if method == "LSB":
                    self.cbs.hide_text_directly(text, cover_path, output_path)
                elif method == "DCT":
                    self.dct_stego.hide_text_dct(cover_path, text, output_path)
                elif method == "Hybrid":
                    self.hybrid_stego.hide_text_hybrid(cover_path, text, output_path)
                hide_time = time.perf_counter() - hide_start
                
                # Calculate metrics
                metrics_start = time.perf_counter()
                metrics = QualityMetrics.calculate_all_metrics(cover_path, output_path)
                metrics_time = time.perf_counter() - metrics_start
                total_time = time.perf_counter() - op_start
                self.psnr_label.config(text=f"PSNR: {metrics['PSNR']:.2f} dB")
                self.ssim_label.config(text=f"SSIM: {metrics['SSIM']:.4f}")
                self.ber_label.config(text=f"BER: {metrics['BER']:.4f}%")
                
                timing_text = self._build_timing_text([
                    ("Embed/hide", hide_time),
                    ("Metrics", metrics_time),
                    ("Total", total_time),
                ])
                messagebox.showinfo("Success", f"Text hidden successfully using {method} method!\n\n{timing_text}")
                self.stego_status.config(text=f"Hidden successfully! (Total: {self._format_elapsed(total_time)})", fg='green')
            except Exception as e:
                messagebox.showerror("Error", str(e))
                self.stego_status.config(text="Error hiding text", fg='red')
    
    def hide_barcode(self):
        text = self.stego_text_input.get('1.0', tk.END).strip()
        cover_path = self.cover_path_var.get()
        
        if not text or not cover_path:
            messagebox.showwarning("Warning", "Please enter text and select a cover image!")
            return
        
        output_path = filedialog.asksaveasfilename(defaultextension=".png",
                                                 filetypes=[("PNG files", "*.png")])
        if output_path:
            try:
                op_start = time.perf_counter()
                # Check if hybrid encryption is requested (from Encode tab)
                use_hybrid = self.use_hybrid_crypto_var.get()
                
                # First encode text to barcode pattern
                encode_start = time.perf_counter()
                pattern = self.cbs.encode(text, use_hybrid_encryption=use_hybrid)
                encode_time = time.perf_counter() - encode_start
                
                # Then hide pattern in image
                hide_start = time.perf_counter()
                self.barcode_stego.hide_barcode_in_image(cover_path, pattern, output_path)
                hide_time = time.perf_counter() - hide_start
                
                # Calculate metrics
                metrics_start = time.perf_counter()
                metrics = QualityMetrics.calculate_all_metrics(cover_path, output_path)
                metrics_time = time.perf_counter() - metrics_start
                total_time = time.perf_counter() - op_start
                self.psnr_label.config(text=f"PSNR: {metrics['PSNR']:.2f} dB")
                self.ssim_label.config(text=f"SSIM: {metrics['SSIM']:.4f}")
                self.ber_label.config(text=f"BER: {metrics['BER']:.4f}%")
                
                timing_text = self._build_timing_text([
                    ("Encode barcode", encode_time),
                    ("Embed/hide", hide_time),
                    ("Metrics", metrics_time),
                    ("Total", total_time),
                ])
                messagebox.showinfo("Success", f"Text encoded as barcode and hidden successfully!\n\n{timing_text}")
                self.stego_status.config(text=f"Hidden successfully! (Total: {self._format_elapsed(total_time)})", fg='green')
            except Exception as e:
                messagebox.showerror("Error", str(e))
                self.stego_status.config(text="Error hiding barcode", fg='red')
    
    def show_cover_image_preview(self, image_path):
        """Display cover image in preview frame"""
        if self.hide_barcode_cover_preview_frame is None:
            return
        
        # Clear previous preview
        for widget in self.hide_barcode_cover_preview_frame.winfo_children():
            widget.destroy()
        
        try:
            # Load and resize image for preview (smaller to save space for comparison section)
            img = Image.open(image_path)
            img.thumbnail((250, 250), Image.LANCZOS)
            
            photo = ImageTk.PhotoImage(img)
            label = tk.Label(self.hide_barcode_cover_preview_frame, image=photo, bg='lightgray')
            label.image = photo  # Keep reference
            label.pack(expand=True)
            
            self.hide_barcode_cover_image_ref = photo  # Keep reference
        except Exception as e:
            error_label = tk.Label(self.hide_barcode_cover_preview_frame, 
                                  text=f"Error loading image:\n{str(e)}", 
                                  bg='lightgray', fg='red', font=('Arial', 9))
            error_label.pack(expand=True)
    
    def get_image_info(self, image_path):
        """Get detailed information about an image"""
        try:
            img = Image.open(image_path)
            width, height = img.size
            total_pixels = width * height
            file_size = os.path.getsize(image_path)
            format_name = img.format or "Unknown"
            
            # Format file size
            if file_size < 1024:
                size_str = f"{file_size} B"
            elif file_size < 1024 * 1024:
                size_str = f"{file_size / 1024:.2f} KB"
            else:
                size_str = f"{file_size / (1024 * 1024):.2f} MB"
            
            return {
                'width': width,
                'height': height,
                'dimensions': f"{width} × {height}",
                'total_pixels': total_pixels,
                'pixels_str': f"{total_pixels:,}",
                'file_size': file_size,
                'size_str': size_str,
                'format': format_name
            }
        except Exception as e:
            return None
    
    def update_image_comparison(self, cover_path, stego_path):
        """Update the image comparison section with cover and stego image information"""
        # Get cover image info
        cover_info = self.get_image_info(cover_path) if cover_path and os.path.exists(cover_path) else None
        stego_info = self.get_image_info(stego_path) if stego_path and os.path.exists(stego_path) else None
        
        # Update cover image info
        if cover_info:
            self.hide_barcode_cover_dimensions_label.config(text=f"Size: {cover_info['dimensions']}")
            self.hide_barcode_cover_size_label.config(text=f"File: {cover_info['size_str']}")
            self.hide_barcode_cover_pixels_label.config(text=f"Pixels: {cover_info['pixels_str']}")
        else:
            self.hide_barcode_cover_dimensions_label.config(text="Size: N/A")
            self.hide_barcode_cover_size_label.config(text="File: N/A")
            self.hide_barcode_cover_pixels_label.config(text="Pixels: N/A")
        
        # Update stego image info
        if stego_info:
            self.hide_barcode_stego_dimensions_label.config(text=f"Size: {stego_info['dimensions']}")
            self.hide_barcode_stego_size_label.config(text=f"File: {stego_info['size_str']}")
            self.hide_barcode_stego_pixels_label.config(text=f"Pixels: {stego_info['pixels_str']}")
        else:
            self.hide_barcode_stego_dimensions_label.config(text="Size: N/A")
            self.hide_barcode_stego_size_label.config(text="File: N/A")
            self.hide_barcode_stego_pixels_label.config(text="Pixels: N/A")
        
        # Calculate and display differences
        if cover_info and stego_info:
            # Size difference
            size_diff = stego_info['file_size'] - cover_info['file_size']
            if abs(size_diff) < 1024:
                size_diff_str = f"{size_diff:+.0f} B"
            elif abs(size_diff) < 1024 * 1024:
                size_diff_str = f"{size_diff / 1024:+.2f} KB"
            else:
                size_diff_str = f"{size_diff / (1024 * 1024):+.2f} MB"
            
            if size_diff > 0:
                self.hide_barcode_size_diff_label.config(text=f"Size: {size_diff_str} ↑", fg='darkred')
            elif size_diff < 0:
                self.hide_barcode_size_diff_label.config(text=f"Size: {size_diff_str} ↓", fg='darkgreen')
            else:
                self.hide_barcode_size_diff_label.config(text="Size: No change", fg='darkblue')
            
            # Dimension difference
            width_diff = stego_info['width'] - cover_info['width']
            height_diff = stego_info['height'] - cover_info['height']
            if width_diff == 0 and height_diff == 0:
                self.hide_barcode_dimension_diff_label.config(text="Dim: Same", fg='darkblue')
            else:
                dim_diff_str = f"W:{width_diff:+d} H:{height_diff:+d}"
                self.hide_barcode_dimension_diff_label.config(text=f"Dim: {dim_diff_str}", fg='darkred')
            
            # Pixel difference
            pixel_diff = stego_info['total_pixels'] - cover_info['total_pixels']
            if pixel_diff == 0:
                self.hide_barcode_pixel_diff_label.config(text="Pixels: Same", fg='darkblue')
            else:
                pixel_pct = pixel_diff / cover_info['total_pixels'] * 100
                if abs(pixel_diff) < 1000:
                    pixel_diff_str = f"{pixel_diff:+,} ({pixel_pct:+.2f}%)"
                else:
                    pixel_diff_str = f"{pixel_diff/1000:+.1f}K ({pixel_pct:+.2f}%)"
                if pixel_diff > 0:
                    self.hide_barcode_pixel_diff_label.config(text=f"Pixels: +{pixel_diff_str} ↑", fg='darkred')
                else:
                    self.hide_barcode_pixel_diff_label.config(text=f"Pixels: {pixel_diff_str} ↓", fg='darkgreen')
        else:
            self.hide_barcode_size_diff_label.config(text="Size: N/A")
            self.hide_barcode_dimension_diff_label.config(text="Dim: N/A")
            self.hide_barcode_pixel_diff_label.config(text="Pixels: N/A")
        
        # Calculate and display advanced metrics
        if cover_path and stego_path and os.path.exists(cover_path) and os.path.exists(stego_path):
            try:
                # Calculate advanced metrics
                metrics = QualityMetrics.calculate_all_metrics(cover_path, stego_path)
                
                # Entropy comparison (compact format)
                entropy_cover = metrics.get('Entropy_Original', 0)
                entropy_stego = metrics.get('Entropy_Stego', 0)
                entropy_diff = entropy_stego - entropy_cover
                
                self.hide_barcode_entropy_cover_label.config(
                    text=f"Entropy C: {entropy_cover:.3f}")
                self.hide_barcode_entropy_stego_label.config(
                    text=f"S: {entropy_stego:.3f} ({entropy_diff:+.3f})")
                
                # Histogram variance (compact format)
                hist_cover = metrics.get('Hist_Original', {})
                hist_stego = metrics.get('Hist_Stego', {})
                var_cover = hist_cover.get('variance', 0)
                var_stego = hist_stego.get('variance', 0)
                var_diff = var_stego - var_cover
                var_pct = (var_diff / var_cover * 100) if var_cover > 0 else 0
                
                self.hide_barcode_hist_variance_label.config(
                    text=f"Hist Var: {var_cover:.0f}→{var_stego:.0f} ({var_pct:+.1f}%)")
                
                # Chi-square test for LSB detection (compact format)
                chi_suspicion = metrics.get('Chi_Square_Suspicion', 0)
                if chi_suspicion < 0.3:
                    chi_text = f"LSB: Low({chi_suspicion:.2f})"
                    chi_color = 'darkgreen'
                elif chi_suspicion < 0.7:
                    chi_text = f"LSB: Med({chi_suspicion:.2f})"
                    chi_color = 'orange'
                else:
                    chi_text = f"LSB: High({chi_suspicion:.2f})"
                    chi_color = 'darkred'
                
                self.hide_barcode_chi_square_label.config(text=chi_text, fg=chi_color)
                
                # Display embedded data size (use stored value if available, otherwise estimate from file size)
                if hasattr(self, 'embedded_data_size_bytes') and self.embedded_data_size_bytes > 0:
                    embedded_bytes = self.embedded_data_size_bytes
                    if embedded_bytes < 1024:
                        embedded_str = f"{embedded_bytes} B"
                    elif embedded_bytes < 1024 * 1024:
                        embedded_str = f"{embedded_bytes / 1024:.2f} KB"
                    else:
                        embedded_str = f"{embedded_bytes / (1024 * 1024):.2f} MB"
                    self.hide_barcode_embedded_size_label.config(
                        text=f"Embedded: {embedded_str}", fg='orange')
                elif cover_info and stego_info:
                    # Fallback: estimate from file size difference
                    embedded_bytes = stego_info['file_size'] - cover_info['file_size']
                    if embedded_bytes > 0:
                        if embedded_bytes < 1024:
                            embedded_str = f"{embedded_bytes} B"
                        elif embedded_bytes < 1024 * 1024:
                            embedded_str = f"{embedded_bytes / 1024:.2f} KB"
                        else:
                            embedded_str = f"{embedded_bytes / (1024 * 1024):.2f} MB"
                        self.hide_barcode_embedded_size_label.config(
                            text=f"Embedded: ~{embedded_str}", fg='orange')
                    else:
                        self.hide_barcode_embedded_size_label.config(
                            text="Embedded: Minimal", fg='darkgreen')
                else:
                    self.hide_barcode_embedded_size_label.config(text="Embedded: N/A")
                    
            except Exception as e:
                # If calculation fails, set to N/A
                self.hide_barcode_entropy_cover_label.config(text="Entropy C: N/A")
                self.hide_barcode_entropy_stego_label.config(text="S: N/A")
                self.hide_barcode_hist_variance_label.config(text="Hist Var: N/A")
                self.hide_barcode_chi_square_label.config(text="LSB: N/A")
                self.hide_barcode_embedded_size_label.config(text="Embedded: N/A")
        else:
            # Reset to N/A if images not available
            self.hide_barcode_entropy_cover_label.config(text="Entropy C: N/A")
            self.hide_barcode_entropy_stego_label.config(text="S: N/A")
            self.hide_barcode_hist_variance_label.config(text="Hist Var: N/A")
            self.hide_barcode_chi_square_label.config(text="LSB: N/A")
            self.hide_barcode_embedded_size_label.config(text="Embedded: N/A")
    
    def show_stego_image_preview(self, image_path):
        """Display stego image in preview frame"""
        if self.hide_barcode_stego_preview_frame is None:
            return
        
        # Clear previous preview
        for widget in self.hide_barcode_stego_preview_frame.winfo_children():
            widget.destroy()
        
        try:
            # Load and resize image for preview (smaller to save space for comparison section)
            img = Image.open(image_path)
            img.thumbnail((250, 250), Image.LANCZOS)
            
            photo = ImageTk.PhotoImage(img)
            label = tk.Label(self.hide_barcode_stego_preview_frame, image=photo, bg='lightgray')
            label.image = photo  # Keep reference
            label.pack(expand=True)
            
            self.hide_barcode_stego_image_ref = photo  # Keep reference
        except Exception as e:
            error_label = tk.Label(self.hide_barcode_stego_preview_frame, 
                                  text=f"Error loading image:\n{str(e)}", 
                                  bg='lightgray', fg='red', font=('Arial', 9))
            error_label.pack(expand=True)
    
    def hide_barcode_file(self):
        barcode_path = self.barcode_file_var.get()
        cover_path = self.cover_path_var2.get()
        
        if not barcode_path or not cover_path:
            messagebox.showwarning("Warning", "Please select both barcode file and cover image!")
            return
        
        output_path = filedialog.asksaveasfilename(defaultextension=".png",
                                                 filetypes=[("PNG files", "*.png")])
        if output_path:
            try:
                op_start = time.perf_counter()
                # Load barcode pattern from file
                load_start = time.perf_counter()
                pattern = self.cbs.load_barcode(barcode_path)
                load_time = time.perf_counter() - load_start
                
                # Calculate actual embedded data size (barcode pattern size)
                # Pattern is a list of 0s and 1s, convert to bytes estimate
                pattern_bits = len(pattern)
                pattern_bytes = (pattern_bits + 7) // 8  # Convert bits to bytes (rounded up)
                # Add overhead for headers/metadata (magic bytes, length, etc.)
                # LSB: ~10-20 bytes overhead, DCT: ~50-100 bytes, Hybrid: ~100-200 bytes
                method = self.hide_barcode_method_var.get()
                if method == "LSB":
                    overhead = 20
                elif method == "DCT":
                    overhead = 100
                else:  # Hybrid
                    overhead = 200
                estimated_embedded_bytes = pattern_bytes + overhead
                
                hide_start = time.perf_counter()
                if method == "LSB":
                    # Hide pattern in image using LSB
                    self.barcode_stego.hide_barcode_in_image(cover_path, pattern, output_path)
                elif method == "DCT":
                    # Use DCT method (with optional JPEG-robust mode)
                    if self.jpeg_robust_var.get():
                        # Use JPEG-robust mode
                        self.dct_stego_jpeg.hide_barcode_in_image(cover_path, pattern, output_path)
                    else:
                        # Use normal DCT method
                        self.dct_stego.hide_barcode_in_image(cover_path, pattern, output_path)
                elif method == "Hybrid":
                    # Use new Hybrid method
                    self.hybrid_stego.hide_barcode_in_image(cover_path, pattern, output_path)
                hide_time = time.perf_counter() - hide_start
                
                # Calculate metrics
                metrics_start = time.perf_counter()
                metrics = QualityMetrics.calculate_all_metrics(cover_path, output_path)
                metrics_time = time.perf_counter() - metrics_start
                self.hide_barcode_psnr_label.config(text=f"PSNR: {metrics['PSNR']:.2f} dB")
                self.hide_barcode_ssim_label.config(text=f"SSIM: {metrics['SSIM']:.4f}")
                self.hide_barcode_ber_label.config(text=f"BER: {metrics['BER']:.4f}%")
                
                # Display stego image preview
                preview_start = time.perf_counter()
                self.show_stego_image_preview(output_path)
                
                # Update image comparison with both cover and stego info
                # Store embedded size for display
                self.embedded_data_size_bytes = estimated_embedded_bytes
                self.update_image_comparison(cover_path, output_path)
                preview_compare_time = time.perf_counter() - preview_start
                total_time = time.perf_counter() - op_start
                
                timing_text = self._build_timing_text([
                    ("Upload/load barcode", load_time),
                    ("Embed/hide", hide_time),
                    ("Metrics", metrics_time),
                    ("Preview/comparison", preview_compare_time),
                    ("Total", total_time),
                ])
                messagebox.showinfo("Success", f"Barcode file hidden successfully!\n\n{timing_text}")
                self.hide_barcode_status.config(text=f"Hidden successfully! (Total: {self._format_elapsed(total_time)})", fg='green')
            except Exception as e:
                messagebox.showerror("Error", str(e))
                self.hide_barcode_status.config(text="Error hiding barcode", fg='red')

    def clear_stego(self):
        self.stego_text_input.delete('1.0', tk.END)
        self.stego_status.config(text="Select a cover image", fg='black')
        self.psnr_label.config(text="PSNR: N/A")
        self.ssim_label.config(text="SSIM: N/A")
        self.ber_label.config(text="BER: N/A")

    def extract_text(self):
        stego_path = self.stego_path_var.get()
        if not stego_path:
            messagebox.showwarning("Warning", "Please select a stego image first!")
            return
        
        # Use denoised image if available
        image_to_use = self.denoised_image_path if self.denoised_image_path and os.path.exists(self.denoised_image_path) else stego_path
        
        try:
            op_start = time.perf_counter()
            method = self.extract_method_var.get()
            text = ""
            
            extract_start = time.perf_counter()
            if method == "LSB":
                text = self.cbs.extract_text_directly(image_to_use)
            elif method == "DCT":
                text = self.dct_stego.extract_text_dct(image_to_use)
            elif method == "Hybrid":
                text = self.hybrid_stego.extract_text_hybrid(image_to_use)
            extract_time = time.perf_counter() - extract_start
            total_time = time.perf_counter() - op_start
            
            status_msg = "Extracted successfully!"
            if image_to_use != stego_path:
                status_msg += " (using denoised image)"
            status_msg += f" | Total: {self._format_elapsed(total_time)}"
            self.extract_status.config(text=status_msg, fg='green')
            timing_text = self._build_timing_text([
                ("Extract", extract_time),
                ("Total", total_time),
            ])
            self._write_extract_output(text, timing_text)
            messagebox.showinfo("Success", f"Text extracted successfully using {method} method!\n\n{timing_text}")
        except Exception as e:
            messagebox.showerror("Error", str(e))
            self.extract_status.config(text="Error extracting", fg='red')

    def extract_barcode(self):
        stego_path = self.stego_path_var.get()
        if not stego_path:
            messagebox.showwarning("Warning", "Please select a stego image first!")
            return
        
        # Use denoised image if available
        image_to_use = self.denoised_image_path if self.denoised_image_path and os.path.exists(self.denoised_image_path) else stego_path
        
        try:
            op_start = time.perf_counter()
            # Extract barcode pattern
            method = self.extract_method_var.get()
            extract_time = 0.0
            decode_time = 0.0
            image_parse_time = None
            
            if method == "LSB":
                extract_start = time.perf_counter()
                text = self.cbs.extract_from_stego_image(image_to_use)
                
                # Also get the pattern for saving
                stego = BarcodeSteganography()
                self.extracted_barcode_pattern = stego.extract_barcode_from_image(image_to_use)
                self.extracted_barcode_scale = stego.get_last_extracted_scale()
                extract_time = time.perf_counter() - extract_start
                
            elif method == "DCT":
                # Use new DCT extraction
                extract_start = time.perf_counter()
                self.extracted_barcode_pattern = self.dct_stego.extract_barcode_from_image(image_to_use)
                self.extracted_barcode_scale = self.dct_stego.get_last_extracted_scale()
                extract_time = time.perf_counter() - extract_start
                
                # Decode the pattern
                decode_start = time.perf_counter()
                text = self.cbs.decode(self.extracted_barcode_pattern, use_hybrid_decryption=True)
                decode_time = time.perf_counter() - decode_start
                
            elif method == "Hybrid":
                # Use new Hybrid extraction
                extract_start = time.perf_counter()
                self.extracted_barcode_pattern = self.hybrid_stego.extract_barcode_from_image(image_to_use)
                self.extracted_barcode_scale = self.hybrid_stego.get_last_extracted_scale()
                extract_time = time.perf_counter() - extract_start
                
                # Decode the pattern
                decode_start = time.perf_counter()
                text = self.cbs.decode(self.extracted_barcode_pattern, use_hybrid_decryption=True)
                decode_time = time.perf_counter() - decode_start
            
            # Check if it's an image
            if text.startswith("[IMAGE:"):
                # Check if it's still encrypted (decryption failed)
                if "[BLOCK_ENC:" in text or "[HYBRID_ENCRYPTED" in text:
                     messagebox.showwarning("Decryption Failed", 
                         "The barcode contains encrypted data that could not be decrypted.\n\n"
                         "This means the barcode was created with DIFFERENT encryption keys.\n\n"
                         "To decrypt this barcode:\n"
                         "1. Find the original private_key.pem and public_key.pem files\n"
                         "2. Use 'Manage RSA Keys' → 'Import Keys' to load them\n\n"
                         "OR create a new barcode without encryption (uncheck the encryption option).")
                     # Fall through to display text
                else:
                    try:
                        parse_start = time.perf_counter()
                        # Find the end of the header
                        header_end = text.find(']')
                        if header_end != -1:
                            header = text[:header_end+1]
                            encoded_string = text[header_end+1:].strip()
                            
                            meta = header[7:-1].split(':')
                            if len(meta) >= 3:
                                orig_filename = meta[0]
                                img_format = meta[1]
                                
                                try:
                                    # Sanitize: Remove any non-base64 characters
                                    import re
                                    encoded_string = re.sub(r'[^A-Za-z0-9+/=]', '', encoded_string)
                                    
                                    image_data = base64.b64decode(encoded_string)
                                    
                                    image_parse_time = time.perf_counter() - parse_start
                                    total_time = time.perf_counter() - op_start
                                    self.extract_status.config(
                                        text=f"Image extracted successfully! (Total: {self._format_elapsed(total_time)})",
                                        fg='green'
                                    )
                                    timing_text = self._build_timing_text([
                                        ("Extract barcode", extract_time),
                                        ("Decode payload", decode_time if decode_time > 0 else None),
                                        ("Image parse", image_parse_time),
                                        ("Total", total_time),
                                    ])
                                    image_info = f"Decoded Image: {orig_filename}\nFormat: {img_format}\nSize: {len(image_data):,} bytes"
                                    self._write_extract_output(image_info, timing_text)
                                    messagebox.showinfo("Success", f"Barcode extracted and decoded successfully!\n\n{timing_text}")
                                    return
                                except Exception as e:
                                    print(f"Base64 error in extract: {e}")
                        else:
                             print("Header end ']' not found in extract")
                    except Exception as e:
                        print(f"Image parsing error in extract: {e}")
            # Fall through to display text if not an image or parsing failed
            status_msg = "Extracted successfully!"
            if image_to_use != stego_path:
                status_msg += " (using denoised image)"
            total_time = time.perf_counter() - op_start
            status_msg += f" | Total: {self._format_elapsed(total_time)}"
            self.extract_status.config(text=status_msg, fg='green')
            timing_text = self._build_timing_text([
                ("Extract barcode", extract_time),
                ("Decode payload", decode_time if decode_time > 0 else None),
                ("Total", total_time),
            ])
            self._write_extract_output(text, timing_text)
            messagebox.showinfo("Success", f"Barcode extracted and decoded successfully!\n\n{timing_text}")
            
        except Exception as e:
            messagebox.showerror("Error", str(e))
            self.extract_status.config(text="Error extracting", fg='red')
    
    def auto_denoise_and_extract(self):
        """Automatically try different denoising parameters until extraction succeeds"""
        stego_path = self.stego_path_var.get()
        if not stego_path or not os.path.exists(stego_path):
            messagebox.showwarning("Warning", "Please select a stego image first!")
            return
        
        # Create progress window
        progress_window = tk.Toplevel(self.root)
        progress_window.title("Auto-Denoise & Extract - Progress")
        progress_window.geometry("600x400")
        progress_window.configure(bg='white')
        
        tk.Label(progress_window, text="🤖 Auto-Denoise & Extract", 
                font=('Arial', 16, 'bold'), bg='white', fg='black').pack(pady=10)
        
        tk.Label(progress_window, text="Trying different denoising parameters automatically...", 
                font=('Arial', 10), bg='white', fg='gray').pack(pady=5)
        
        progress_text = scrolledtext.ScrolledText(progress_window, height=15, width=70, 
                                                  font=('Consolas', 9), bg='black', fg='lightgreen')
        progress_text.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        progress_text.insert(tk.END, "Starting automatic denoising and extraction...\n")
        progress_text.insert(tk.END, "="*60 + "\n\n")
        progress_window.update()
        
        method = self.extract_method_var.get()
        overall_start = time.perf_counter()
        
        def fmt_elapsed(seconds):
            return f"{seconds:.2f}s"
        
        def log(message):
            progress_text.insert(tk.END, message + "\n")
            progress_text.see(tk.END)
            progress_window.update()
        
        def try_extraction(image_path, try_barcode=True):
            """Try extraction and return (success, result_text, extraction_type)"""
            # Try barcode extraction first (more common)
            if try_barcode:
                try:
                    if method == "LSB":
                        text = self.cbs.extract_from_stego_image(image_path)
                        if text and len(text.strip()) > 0:
                            # Try to decode
                            stego = BarcodeSteganography()
                            pattern = stego.extract_barcode_from_image(image_path)
                            if pattern is not None:
                                decoded = self.cbs.decode(pattern, use_hybrid_decryption=True)
                                if decoded and len(decoded.strip()) > 0:
                                    return True, decoded, "barcode"
                    elif method == "DCT":
                        pattern = self.dct_stego.extract_barcode_from_image(image_path)
                        if pattern is not None:
                            decoded = self.cbs.decode(pattern, use_hybrid_decryption=True)
                            if decoded and len(decoded.strip()) > 0:
                                return True, decoded, "barcode"
                    elif method == "Hybrid":
                        pattern = self.hybrid_stego.extract_barcode_from_image(image_path)
                        if pattern is not None:
                            decoded = self.cbs.decode(pattern, use_hybrid_decryption=True)
                            if decoded and len(decoded.strip()) > 0:
                                return True, decoded, "barcode"
                except:
                    pass
            
            # Try direct text extraction
            try:
                if method == "LSB":
                    text = self.cbs.extract_text_directly(image_path)
                elif method == "DCT":
                    text = self.dct_stego.extract_text_dct(image_path)
                elif method == "Hybrid":
                    text = self.hybrid_stego.extract_text_hybrid(image_path)
                else:
                    return False, "", "none"
                
                if text and len(text.strip()) > 0 and not text.startswith("Error"):
                    # Check if it's a valid extraction (not just error messages)
                    error_keywords = ["Invalid", "not found", "cannot", "failed", "Error"]
                    if not any(keyword.lower() in text.lower() for keyword in error_keywords):
                        return True, text, "text"
            except:
                pass
            
            return False, "", "none"
        
        # Step 1: Try extraction without denoising first
        step1_start = time.perf_counter()
        log("Step 1: Trying extraction WITHOUT denoising...")
        success, result, ext_type = try_extraction(stego_path, try_barcode=True)
        step1_elapsed = time.perf_counter() - step1_start
        log(f"⏱️ Step 1 time: {fmt_elapsed(step1_elapsed)}")
        if success:
            log(f"✅ SUCCESS! Extraction worked without denoising! (Type: {ext_type})")
            log(f"Result: {result[:100]}..." if len(result) > 100 else f"Result: {result}")
            log(f"⏱️ Total auto-extract time: {fmt_elapsed(time.perf_counter() - overall_start)}")
            progress_text.insert(tk.END, "\n" + "="*60 + "\n")
            progress_text.insert(tk.END, "✅ Extraction successful without denoising!\n")
            
            # Update the main window
            self.extracted_text.config(state=tk.NORMAL)
            self.extracted_text.delete('1.0', tk.END)
            self.extracted_text.insert('1.0', result)
            self.extracted_text.config(state=tk.DISABLED)
            self.extract_status.config(text="Extracted successfully! (no denoising needed)", fg='green')
            
            tk.Button(progress_window, text="Close", bg='green', fg='white', 
                     font=('Arial', 11, 'bold'), command=progress_window.destroy).pack(pady=10)
            messagebox.showinfo("Success", "Extraction successful without denoising!")
            return
        
        log("❌ Failed. Starting automatic denoising...\n")
        
        # Step 2: Try different denoising combinations
        median_sizes = [3, 5, 7, 9]
        gaussian_sigmas = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
        
        total_attempts = len(median_sizes) + len(gaussian_sigmas)
        attempt_num = 0
        median_total_time = 0.0
        gaussian_total_time = 0.0
        
        # Try median filters first (usually better for salt & pepper)
        log("Step 2: Trying Median Filters...")
        for size in median_sizes:
            attempt_num += 1
            attempt_start = time.perf_counter()
            log(f"\n[{attempt_num}/{total_attempts}] Trying Median Filter (size={size})...")
            progress_window.update()
            
            try:
                img = Image.open(stego_path)
                img_array = np.array(img, dtype=np.float32)
                denoised_array = apply_median_filter(img_array, size)
                denoised_array = np.clip(denoised_array, 0, 255).astype(np.uint8)
                denoised_img = Image.fromarray(denoised_array)
                
                # Save to temp file
                temp_path = os.path.join(os.path.dirname(stego_path), 
                                        f"temp_denoised_median_{size}.png")
                denoised_img.save(temp_path, 'PNG')
                
                success, result, ext_type = try_extraction(temp_path, try_barcode=True)
                if success:
                    log(f"✅ SUCCESS with Median Filter (size={size})! (Extraction type: {ext_type})")
                    log(f"Result: {result[:100]}..." if len(result) > 100 else f"Result: {result}")
                    attempt_elapsed = time.perf_counter() - attempt_start
                    median_total_time += attempt_elapsed
                    log(f"⏱️ Attempt time (Median size={size}): {fmt_elapsed(attempt_elapsed)}")
                    log(f"⏱️ Median filters total time: {fmt_elapsed(median_total_time)}")
                    log(f"⏱️ Total auto-extract time: {fmt_elapsed(time.perf_counter() - overall_start)}")
                    
                    # Save as the denoised image to use
                    final_path = os.path.join(os.path.dirname(stego_path), 
                                            f"denoised_{os.path.basename(stego_path)}")
                    denoised_img.save(final_path, 'PNG')
                    self.denoised_image_path = final_path
                    self.stego_path_var.set(final_path)
                    
                    # Update main window
                    self.extracted_text.config(state=tk.NORMAL)
                    self.extracted_text.delete('1.0', tk.END)
                    self.extracted_text.insert('1.0', result)
                    self.extracted_text.config(state=tk.DISABLED)
                    self.extract_status.config(text=f"✅ Extracted! (Median filter, size={size})", fg='green')
                    
                    progress_text.insert(tk.END, "\n" + "="*60 + "\n")
                    progress_text.insert(tk.END, f"✅ SUCCESS! Used Median Filter (size={size})\n")
                    
                    # Clean up temp files
                    try:
                        os.remove(temp_path)
                    except:
                        pass
                    
                    tk.Button(progress_window, text="Close", bg='green', fg='white', 
                             font=('Arial', 11, 'bold'), command=progress_window.destroy).pack(pady=10)
                    messagebox.showinfo("Success", 
                        f"✅ Extraction successful!\n\n"
                        f"Used: Median Filter (size={size})\n\n"
                        f"Denoised image saved and ready for use.")
                    return
                else:
                    attempt_elapsed = time.perf_counter() - attempt_start
                    median_total_time += attempt_elapsed
                    log(f"⏱️ Attempt time (Median size={size}): {fmt_elapsed(attempt_elapsed)}")
                    log("❌ Failed")
                    # Clean up temp file
                    try:
                        os.remove(temp_path)
                    except:
                        pass
            except Exception as e:
                attempt_elapsed = time.perf_counter() - attempt_start
                median_total_time += attempt_elapsed
                log(f"⏱️ Attempt time (Median size={size}): {fmt_elapsed(attempt_elapsed)}")
                log(f"❌ Error: {str(e)}")
        
        log(f"⏱️ Median filters total time: {fmt_elapsed(median_total_time)}")
        
        # Try Gaussian filters
        log("\nStep 3: Trying Gaussian Filters...")
        for sigma in gaussian_sigmas:
            attempt_num += 1
            attempt_start = time.perf_counter()
            log(f"\n[{attempt_num}/{total_attempts}] Trying Gaussian Filter (σ={sigma})...")
            progress_window.update()
            
            try:
                img = Image.open(stego_path)
                img_array = np.array(img, dtype=np.float32)
                denoised_array = apply_gaussian_filter(img_array, sigma)
                denoised_array = np.clip(denoised_array, 0, 255).astype(np.uint8)
                denoised_img = Image.fromarray(denoised_array)
                
                # Save to temp file
                temp_path = os.path.join(os.path.dirname(stego_path), 
                                        f"temp_denoised_gauss_{sigma}.png")
                denoised_img.save(temp_path, 'PNG')
                
                success, result, ext_type = try_extraction(temp_path, try_barcode=True)
                if success:
                    log(f"✅ SUCCESS with Gaussian Filter (σ={sigma})! (Extraction type: {ext_type})")
                    log(f"Result: {result[:100]}..." if len(result) > 100 else f"Result: {result}")
                    attempt_elapsed = time.perf_counter() - attempt_start
                    gaussian_total_time += attempt_elapsed
                    log(f"⏱️ Attempt time (Gaussian σ={sigma}): {fmt_elapsed(attempt_elapsed)}")
                    log(f"⏱️ Gaussian filters total time: {fmt_elapsed(gaussian_total_time)}")
                    log(f"⏱️ Total auto-extract time: {fmt_elapsed(time.perf_counter() - overall_start)}")
                    
                    # Save as the denoised image to use
                    final_path = os.path.join(os.path.dirname(stego_path), 
                                            f"denoised_{os.path.basename(stego_path)}")
                    denoised_img.save(final_path, 'PNG')
                    self.denoised_image_path = final_path
                    self.stego_path_var.set(final_path)
                    
                    # Update main window
                    self.extracted_text.config(state=tk.NORMAL)
                    self.extracted_text.delete('1.0', tk.END)
                    self.extracted_text.insert('1.0', result)
                    self.extracted_text.config(state=tk.DISABLED)
                    self.extract_status.config(text=f"✅ Extracted! (Gaussian filter, σ={sigma})", fg='green')
                    
                    progress_text.insert(tk.END, "\n" + "="*60 + "\n")
                    progress_text.insert(tk.END, f"✅ SUCCESS! Used Gaussian Filter (σ={sigma})\n")
                    
                    # Clean up temp files
                    try:
                        os.remove(temp_path)
                    except:
                        pass
                    
                    tk.Button(progress_window, text="Close", bg='green', fg='white', 
                             font=('Arial', 11, 'bold'), command=progress_window.destroy).pack(pady=10)
                    messagebox.showinfo("Success", 
                        f"✅ Extraction successful!\n\n"
                        f"Used: Gaussian Filter (σ={sigma})\n\n"
                        f"Denoised image saved and ready for use.")
                    return
                else:
                    attempt_elapsed = time.perf_counter() - attempt_start
                    gaussian_total_time += attempt_elapsed
                    log(f"⏱️ Attempt time (Gaussian σ={sigma}): {fmt_elapsed(attempt_elapsed)}")
                    log("❌ Failed")
                    # Clean up temp file
                    try:
                        os.remove(temp_path)
                    except:
                        pass
            except Exception as e:
                attempt_elapsed = time.perf_counter() - attempt_start
                gaussian_total_time += attempt_elapsed
                log(f"⏱️ Attempt time (Gaussian σ={sigma}): {fmt_elapsed(attempt_elapsed)}")
                log(f"❌ Error: {str(e)}")
        
        log(f"⏱️ Gaussian filters total time: {fmt_elapsed(gaussian_total_time)}")
        log(f"⏱️ Overall auto-extract time: {fmt_elapsed(time.perf_counter() - overall_start)}")
        
        # If we get here, nothing worked
        log("\n" + "="*60)
        log("❌ FAILED: Could not extract data with any denoising method")
        log("="*60)
        log("\nSuggestions:")
        log("1. Try manual denoising with different parameters")
        log("2. Check if the image actually contains hidden data")
        log("3. Try a different extraction method (LSB/DCT/Hybrid)")
        log("4. The image might be too corrupted")
        
        tk.Button(progress_window, text="Close", bg='red', fg='white', 
                 font=('Arial', 11, 'bold'), command=progress_window.destroy).pack(pady=10)
        messagebox.showwarning("Failed", 
            "❌ Could not extract data automatically.\n\n"
            "Tried all denoising combinations but extraction failed.\n\n"
            "Try manual denoising or check if the image contains hidden data.")
    
    def save_extracted_barcode_image(self):
        if self.extracted_barcode_pattern is None:
            messagebox.showwarning("Warning", "No barcode extracted yet! Use 'Extract Barcode' first.")
            return
        
        filename = filedialog.asksaveasfilename(defaultextension=".png",
                                              filetypes=[("PNG files", "*.png")])
        if filename:
            try:
                # Save the extracted pattern
                self.cbs.save_barcode(self.extracted_barcode_pattern, filename, scale=self.extracted_barcode_scale)
                messagebox.showinfo("Success", "Extracted barcode image saved successfully!")
            except Exception as e:
                messagebox.showerror("Error", str(e))
    
    def fix_noise_dialog(self):
        """Open dialog to fix noise in stego image"""
        stego_path = self.stego_path_var.get()
        if not stego_path or not os.path.exists(stego_path):
            messagebox.showwarning("Warning", "Please select a stego image first!")
            return
        
        # Create denoising dialog window
        noise_window = tk.Toplevel(self.root)
        noise_window.title("Fix Noise - Denoising Tool")
        noise_window.geometry("700x600")
        noise_window.configure(bg='white')
        
        # Header with help button
        header_frame = tk.Frame(noise_window, bg='white')
        header_frame.pack(fill=tk.X, padx=20, pady=10)
        
        tk.Label(header_frame, text="Denoise Stego Image", 
                font=('Arial', 16, 'bold'), bg='white', fg='black').pack(side=tk.LEFT)
        
        tk.Button(header_frame, text="❓ Help", bg='lightblue', fg='black', 
                 font=('Arial', 9, 'bold'), command=lambda: self.show_denoising_help()).pack(side=tk.RIGHT)
        
        tk.Label(noise_window, text="Apply denoising to improve extraction from noisy images", 
                font=('Arial', 10), bg='white', fg='gray').pack(pady=5)
        
        # Denoising method selection
        method_frame = tk.Frame(noise_window, bg='white')
        method_frame.pack(fill=tk.X, padx=20, pady=10)
        
        tk.Label(method_frame, text="Denoising Method:", 
                font=('Arial', 11, 'bold'), bg='white', fg='black').pack(side=tk.LEFT, padx=(0, 10))
        
        denoise_method_var = tk.StringVar(value="median")
        tk.Radiobutton(method_frame, text="Median Filter (Salt & Pepper)", 
                      variable=denoise_method_var, value="median",
                      font=('Arial', 10), bg='white', fg='black',
                      activebackground='white', activeforeground='black').pack(side=tk.LEFT, padx=5)
        tk.Radiobutton(method_frame, text="Gaussian Filter (General)", 
                      variable=denoise_method_var, value="gaussian",
                      font=('Arial', 10), bg='white', fg='black',
                      activebackground='white', activeforeground='black').pack(side=tk.LEFT, padx=5)
        
        # Parameters frame
        params_frame = tk.Frame(noise_window, bg='white')
        params_frame.pack(fill=tk.X, padx=20, pady=10)
        
        # Median filter size with explanation
        median_frame = tk.Frame(params_frame, bg='white')
        median_frame.pack(fill=tk.X, pady=5)
        tk.Label(median_frame, text="Median Filter Size:", 
                font=('Arial', 9, 'bold'), bg='white', fg='black', width=20).pack(side=tk.LEFT)
        median_size_var = tk.IntVar(value=3)
        tk.Scale(median_frame, from_=3, to=9, resolution=2, 
                orient=tk.HORIZONTAL, variable=median_size_var,
                length=300, bg='white', fg='black', 
                troughcolor='lightgray', activebackground='blue').pack(side=tk.LEFT, padx=10)
        median_label = tk.Label(median_frame, text="3", 
                               font=('Arial', 9), bg='white', fg='black', width=6)
        median_label.pack(side=tk.LEFT)
        median_size_var.trace('w', lambda *args: median_label.config(
            text=str(median_size_var.get())))
        
        # Explanation for median filter
        median_explanation = tk.Label(params_frame, 
            text="📌 Filter Size = Size of the square window (3×3, 5×5, 7×7, 9×9 pixels).\n"
                 "   Larger = removes more noise but blurs more. Good for salt & pepper noise.",
            font=('Arial', 8), bg='white', fg='darkblue', justify=tk.LEFT, anchor='w')
        median_explanation.pack(fill=tk.X, padx=20, pady=(2, 8))
        
        # Gaussian sigma with explanation
        gauss_frame = tk.Frame(params_frame, bg='white')
        gauss_frame.pack(fill=tk.X, pady=5)
        tk.Label(gauss_frame, text="Gaussian Sigma (σ):", 
                font=('Arial', 9, 'bold'), bg='white', fg='black', width=20).pack(side=tk.LEFT)
        gauss_sigma_var = tk.DoubleVar(value=1.0)
        tk.Scale(gauss_frame, from_=0.5, to=3.0, resolution=0.1, 
                orient=tk.HORIZONTAL, variable=gauss_sigma_var,
                length=300, bg='white', fg='black', 
                troughcolor='lightgray', activebackground='blue').pack(side=tk.LEFT, padx=10)
        gauss_label = tk.Label(gauss_frame, text="1.0", 
                               font=('Arial', 9), bg='white', fg='black', width=6)
        gauss_label.pack(side=tk.LEFT)
        gauss_sigma_var.trace('w', lambda *args: gauss_label.config(
            text=f"{gauss_sigma_var.get():.1f}"))
        
        # Explanation for Gaussian filter
        gauss_explanation = tk.Label(params_frame, 
            text="📌 Sigma (σ) = How much to blur (spread of the Gaussian curve).\n"
                 "   Lower (0.5-1.0) = subtle smoothing, preserves details.\n"
                 "   Higher (2.0-3.0) = stronger smoothing, removes more noise but blurs more.\n"
                 "   Gaussian = bell-shaped curve that smoothly blends nearby pixels.",
            font=('Arial', 8), bg='white', fg='darkblue', justify=tk.LEFT, anchor='w')
        gauss_explanation.pack(fill=tk.X, padx=20, pady=(2, 8))
        
        # Preview frames
        preview_container = tk.Frame(noise_window, bg='white')
        preview_container.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # Original preview
        orig_frame = tk.Frame(preview_container, bg='lightgray', relief='sunken', bd=2)
        orig_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        tk.Label(orig_frame, text="Original (Noisy)", 
                font=('Arial', 10, 'bold'), bg='lightgray', fg='black').pack(pady=5)
        orig_preview = tk.Label(orig_frame, text="Loading...", 
                               bg='lightgray', fg='gray', font=('Arial', 9))
        orig_preview.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Denoised preview
        denoised_frame = tk.Frame(preview_container, bg='lightgray', relief='sunken', bd=2)
        denoised_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0))
        tk.Label(denoised_frame, text="Denoised", 
                font=('Arial', 10, 'bold'), bg='lightgray', fg='black').pack(pady=5)
        denoised_preview = tk.Label(denoised_frame, text="Apply to see result", 
                                    bg='lightgray', fg='gray', font=('Arial', 9))
        denoised_preview.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Load and display original
        try:
            orig_img = Image.open(stego_path)
            orig_img.thumbnail((250, 250), Image.LANCZOS)
            orig_photo = ImageTk.PhotoImage(orig_img)
            orig_preview.config(image=orig_photo, text="")
            orig_preview.image = orig_photo
        except Exception as e:
            orig_preview.config(text=f"Error: {str(e)}")
        
        denoised_img_ref = {'img': None}
        
        def apply_denoising():
            """Apply denoising and update preview"""
            try:
                method = denoise_method_var.get()
                img = Image.open(stego_path)
                img_array = np.array(img, dtype=np.float32)
                
                if method == "median":
                    size = median_size_var.get()
                    denoised_array = apply_median_filter(img_array, size)
                else:  # gaussian
                    sigma = gauss_sigma_var.get()
                    denoised_array = apply_gaussian_filter(img_array, sigma)
                
                # Convert back to image
                denoised_array = np.clip(denoised_array, 0, 255).astype(np.uint8)
                denoised_img = Image.fromarray(denoised_array)
                denoised_img_ref['img'] = denoised_img
                
                # Display preview
                preview_img = denoised_img.copy()
                preview_img.thumbnail((250, 250), Image.LANCZOS)
                denoised_photo = ImageTk.PhotoImage(preview_img)
                denoised_preview.config(image=denoised_photo, text="")
                denoised_preview.image = denoised_photo
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to apply denoising: {str(e)}")
        
        def use_denoised():
            """Use the denoised image for extraction"""
            if denoised_img_ref['img'] is None:
                messagebox.showwarning("Warning", "Please apply denoising first!")
                return
            
            # Save denoised image to temp file
            temp_path = os.path.join(os.path.dirname(stego_path), 
                                    f"denoised_{os.path.basename(stego_path)}")
            try:
                denoised_img_ref['img'].save(temp_path, 'PNG')
                self.denoised_image_path = temp_path
                # Update the path variable to use denoised image
                self.stego_path_var.set(temp_path)
                self.extract_status.config(text=f"Using denoised: {os.path.basename(temp_path)}")
                messagebox.showinfo("Success", 
                    f"✅ Denoised image saved and will be used for extraction!\n\n{temp_path}\n\n"
                    f"You can now try extracting again.")
                noise_window.destroy()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save denoised image: {str(e)}")
        
        # Buttons
        btn_frame = tk.Frame(noise_window, bg='white')
        btn_frame.pack(fill=tk.X, padx=20, pady=10)
        
        tk.Button(btn_frame, text="Apply Denoising", bg='green', fg='white', 
                 font=('Arial', 11, 'bold'), command=apply_denoising).pack(side=tk.LEFT, padx=5)
        
        tk.Button(btn_frame, text="Use This for Extraction", bg='blue', fg='white', 
                 font=('Arial', 11, 'bold'), command=use_denoised).pack(side=tk.LEFT, padx=5)
        
        tk.Button(btn_frame, text="Cancel", bg='gray', fg='white', 
                 font=('Arial', 11, 'bold'), command=noise_window.destroy).pack(side=tk.LEFT, padx=5)
        
        # Auto-apply on parameter change
        median_size_var.trace('w', lambda *args: apply_denoising() if denoise_method_var.get() == "median" else None)
        gauss_sigma_var.trace('w', lambda *args: apply_denoising() if denoise_method_var.get() == "gaussian" else None)
        denoise_method_var.trace('w', lambda *args: apply_denoising())
    
    def show_denoising_help(self):
        """Show detailed help about denoising parameters"""
        help_window = tk.Toplevel(self.root)
        help_window.title("Denoising Help - Understanding Filters")
        help_window.geometry("700x650")
        help_window.configure(bg='white')
        
        # Create scrollable text widget
        help_text = scrolledtext.ScrolledText(help_window, wrap=tk.WORD, 
                                             font=('Arial', 10), bg='white', fg='black',
                                             padx=20, pady=20)
        help_text.pack(fill=tk.BOTH, expand=True)
        
        help_content = """
═══════════════════════════════════════════════════════════════
           DENOISING FILTERS - COMPLETE EXPLANATION
═══════════════════════════════════════════════════════════════

1. MEDIAN FILTER
───────────────────────────────────────────────────────────────

WHAT IS IT?
   The median filter removes noise by replacing each pixel with the 
   median (middle value) of its neighbors.

HOW DOES IT WORK?
   • The filter looks at a square window around each pixel
   • It collects all pixel values in that window
   • Sorts them from lowest to highest
   • Takes the middle value (median)
   • Replaces the center pixel with that median value

FILTER SIZE EXPLANATION:
   • Size 3 = 3×3 pixel window (9 pixels total)
     - Looks at 8 neighbors + the center pixel
     - Mild smoothing, preserves most details
     - Best for: Light salt & pepper noise
   
   • Size 5 = 5×5 pixel window (25 pixels total)
     - Looks at 24 neighbors + center
     - Moderate smoothing
     - Best for: Medium salt & pepper noise
   
   • Size 7 = 7×7 pixel window (49 pixels total)
     - Strong smoothing
     - Best for: Heavy salt & pepper noise
   
   • Size 9 = 9×9 pixel window (81 pixels total)
     - Very strong smoothing
     - Best for: Very heavy noise (may blur too much)

WHY USE MEDIAN FILTER?
   ✓ Excellent for "salt and pepper" noise (random black/white dots)
   ✓ Preserves edges better than averaging
   ✓ Removes outliers (extreme pixel values)
   ✗ Can blur fine details if size is too large


2. GAUSSIAN FILTER
───────────────────────────────────────────────────────────────

WHAT IS "GAUSSIAN"?
   Gaussian refers to the bell-shaped curve (normal distribution) 
   used in mathematics. It's named after mathematician Carl Gauss.
   
   The curve looks like this:
   
        ╱╲
       ╱  ╲
      ╱    ╲
     ╱      ╲
    ╱        ╲
   ─────────────
   
   It's highest in the center and smoothly decreases on both sides.

HOW DOES GAUSSIAN FILTER WORK?
   • Creates a weighted average of nearby pixels
   • Pixels closer to the center get MORE weight
   • Pixels farther away get LESS weight
   • The weights follow a Gaussian (bell) curve
   • This creates smooth, natural-looking blur

SIGMA (σ) EXPLANATION:
   Sigma controls how "spread out" the Gaussian curve is.
   Think of it as the "blur radius" or "smoothing strength".

   • Sigma = 0.5
     - Very small blur radius
     - Subtle smoothing
     - Preserves fine details
     - Good for: Light noise, preserving sharp edges
   
   • Sigma = 1.0 (Default)
     - Moderate blur radius
     - Balanced smoothing
     - Good general-purpose setting
     - Good for: Medium noise, general use
   
   • Sigma = 2.0
     - Large blur radius
     - Strong smoothing
     - Removes more noise but blurs more
     - Good for: Heavy noise
   
   • Sigma = 3.0
     - Very large blur radius
     - Very strong smoothing
     - Maximum noise removal
     - Warning: May blur too much, losing important details

VISUAL ANALOGY:
   Imagine you're looking at a picture through frosted glass:
   • Low sigma (0.5) = Lightly frosted glass (still see details)
   • Medium sigma (1.0) = Moderately frosted glass
   • High sigma (3.0) = Heavily frosted glass (blurry)

WHY USE GAUSSIAN FILTER?
   ✓ Smooth, natural-looking blur
   ✓ Good for general noise (not just salt & pepper)
   ✓ Preserves overall image structure
   ✓ Works well with Gaussian noise
   ✗ Can blur edges and fine details
   ✗ Less effective for extreme outliers


3. WHEN TO USE WHICH?
───────────────────────────────────────────────────────────────

USE MEDIAN FILTER WHEN:
   • You see random black and white dots (salt & pepper noise)
   • Noise appears as extreme pixel values
   • You want to preserve sharp edges
   • The noise is sparse (not everywhere)

USE GAUSSIAN FILTER WHEN:
   • Noise is more uniform/spread out
   • You have general image noise (not just dots)
   • You want smooth, natural-looking results
   • The noise follows a Gaussian distribution

TRY BOTH:
   • If one doesn't work well, try the other
   • Sometimes combining both helps
   • Start with lower values and increase if needed
   • Always check the preview before applying!


4. PRACTICAL TIPS
───────────────────────────────────────────────────────────────

STARTING VALUES:
   • Median: Start with size 3, increase if needed
   • Gaussian: Start with sigma 1.0, adjust as needed

TOO MUCH BLUR?
   • Lower the filter size (median) or sigma (Gaussian)
   • You want to remove noise, not lose important details

NOT ENOUGH NOISE REMOVAL?
   • Increase filter size (median) or sigma (Gaussian)
   • But be careful - too much can hurt extraction!

FOR STEGANOGRAPHY:
   • We want to remove noise that interferes with extraction
   • But we must preserve the hidden data in LSBs
   • Test different values and see which works best
   • The preview helps you find the right balance


═══════════════════════════════════════════════════════════════
        Remember: The goal is to improve extraction,
        not to make the image look perfect!
═══════════════════════════════════════════════════════════════
"""
        
        help_text.insert('1.0', help_content)
        help_text.config(state=tk.DISABLED)
        
        tk.Button(help_window, text="Close", bg='blue', fg='white', 
                 font=('Arial', 11, 'bold'), command=help_window.destroy).pack(pady=10)
    
    def run_diagnostic(self):
        file_path = self.diag_path_var.get()
        if not file_path:
            messagebox.showwarning("Warning", "Please select an image to analyze!")
            return
        
        self.diag_output.delete('1.0', tk.END)
        self.diag_output.insert('1.0', f"Analyzing {os.path.basename(file_path)}...\n")
        self.diag_output.insert(tk.END, "="*50 + "\n")
        
        try:
            img = Image.open(file_path)
            self.diag_output.insert(tk.END, f"Format: {img.format}\n")
            self.diag_output.insert(tk.END, f"Mode: {img.mode}\n")
            self.diag_output.insert(tk.END, f"Size: {img.size[0]}x{img.size[1]}\n")
            
            if img.format == 'JPEG':
                self.diag_output.insert(tk.END, "⚠️ WARNING: JPEG format detected!\n")
                self.diag_output.insert(tk.END, "   JPEG compression destroys steganographic data.\n")
                self.diag_output.insert(tk.END, "   Data recovery is likely impossible.\n")
            
            # Convert to RGB array
            img_rgb = img.convert('RGB')
            arr = np.array(img_rgb)
            
            # Analyze LSBs
            self.diag_output.insert(tk.END, "\nLSB Analysis:\n")
            lsb_r = arr[:,:,0] & 1
            lsb_g = arr[:,:,1] & 1
            lsb_b = arr[:,:,2] & 1
            
            r_mean = np.mean(lsb_r)
            g_mean = np.mean(lsb_g)
            b_mean = np.mean(lsb_b)
            
            self.diag_output.insert(tk.END, f"Red Channel LSB Mean: {r_mean:.4f}\n")
            self.diag_output.insert(tk.END, f"Green Channel LSB Mean: {g_mean:.4f}\n")
            self.diag_output.insert(tk.END, f"Blue Channel LSB Mean: {b_mean:.4f}\n")
            
            if abs(r_mean - 0.5) < 0.1:
                self.diag_output.insert(tk.END, "✅ Red channel looks like random data (good for stego)\n")
            else:
                self.diag_output.insert(tk.END, "⚠️ Red channel LSBs are not random (might be empty or compressed)\n")
                
            # Check for magic headers
            self.diag_output.insert(tk.END, "\nSearching for Magic Headers:\n")
            
            # Flatten array for searching
            flat_r = lsb_r.flatten()
            
            # Search for BCSTEGO
            header_bits = []
            for byte in b'BCSTEGO\x01':
                for i in range(7, -1, -1):
                    header_bits.append((byte >> i) & 1)
            
            # Simple search in first 1000 bits
            found = False
            search_limit = min(len(flat_r), 10000)
            
            # Convert bits to string for easier searching (slow but simple)
            bits_str = "".join(map(str, flat_r[:search_limit]))
            header_str = "".join(map(str, header_bits))
            
            if header_str in bits_str:
                pos = bits_str.find(header_str)
                self.diag_output.insert(tk.END, f"✅ Found 'BCSTEGO' header at bit position {pos}\n")
            else:
                self.diag_output.insert(tk.END, "❌ 'BCSTEGO' header not found in first 10,000 bits\n")
            
            # Search for DCTSTEGO
            header_bits = []
            for byte in b'DCTSTEGO':
                for i in range(7, -1, -1):
                    header_bits.append((byte >> i) & 1)
            header_str = "".join(map(str, header_bits))
            
            if header_str in bits_str:
                pos = bits_str.find(header_str)
                self.diag_output.insert(tk.END, f"✅ Found 'DCTSTEGO' header at bit position {pos}\n")
            else:
                self.diag_output.insert(tk.END, "❌ 'DCTSTEGO' header not found in first 10,000 bits\n")
            
            self.diag_output.insert(tk.END, "\nAnalysis Complete.\n")
            
        except Exception as e:
            self.diag_output.insert(tk.END, f"\nError during analysis: {str(e)}\n")