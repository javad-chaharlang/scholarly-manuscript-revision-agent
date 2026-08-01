'''Stable visual tokens for the local Streamlit interface.'''

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Palette:
    navy: str = '#0F172A'
    indigo: str = '#4F46E5'
    blue: str = '#2563EB'
    cyan: str = '#06B6D4'
    background: str = '#F6F8FC'
    card: str = '#FFFFFF'
    text: str = '#111827'
    text_secondary: str = '#64748B'
    success: str = '#059669'
    warning: str = '#D97706'
    danger: str = '#DC2626'
    reviewer_1: str = '#FFFF00'
    reviewer_2: str = '#00FF00'
    shared: str = '#EE82EE'


COLORS = Palette()
SPACING = {'xs': 4, 'sm': 8, 'md': 16, 'lg': 24, 'xl': 32}
RADIUS = {'sm': 6, 'md': 10, 'lg': 14}
SHADOW = '0 4px 16px rgba(15, 23, 42, 0.06)'

