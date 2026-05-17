#!/usr/bin/env python3
"""
Steganography System - Entry point.
Run from the stego_project directory: python main.py
"""
import tkinter as tk
from ui.app import BarcodeSteganographyApp

if __name__ == "__main__":
    root = tk.Tk()
    app = BarcodeSteganographyApp(root)
    root.mainloop()
