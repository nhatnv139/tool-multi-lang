# -*- coding: utf-8 -*-
"""Render tat ca bai trong thu muc data/  ->  python build_all.py"""
import os, glob
from generate import build

ROOT = os.path.dirname(os.path.abspath(__file__))
files = sorted(glob.glob(os.path.join(ROOT, "data", "lesson*.json")))
print(f"Tim thay {len(files)} bai hoc\n")
for f in files:
    build(f)
    print()
print("== XONG TAT CA ==")
