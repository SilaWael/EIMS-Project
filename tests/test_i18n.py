# -*- coding: utf-8 -*-
"""Tests for i18n.py module."""
import pytest

from i18n import t, SUPPORTED_LANGS, is_rtl, get_lang_direction, TRANSLATIONS


class TestI18n:
    def test_supported_langs(self):
        assert 'en' in SUPPORTED_LANGS
        assert 'ar' in SUPPORTED_LANGS

    def test_translate_en(self):
        assert t('nav.dashboard', 'en') == 'Master Dashboard'

    def test_translate_ar(self):
        assert t('nav.dashboard', 'ar') == 'لوحة المعلومات الرئيسية'

    def test_translate_fallback_to_en(self):
        # Use a non-existent language code
        assert t('nav.dashboard', 'fr') == 'Master Dashboard'

    def test_translate_missing_key(self):
        assert t('nonexistent.key', 'en') == 'nonexistent.key'

    def test_is_rtl(self):
        assert is_rtl('ar') is True
        assert is_rtl('en') is False

    def test_get_lang_direction(self):
        assert get_lang_direction('ar') == 'rtl'
        assert get_lang_direction('en') == 'ltr'

    def test_en_ar_parity(self):
        """EN and AR translations must have the same keys."""
        en_keys = set(TRANSLATIONS['en'].keys())
        ar_keys = set(TRANSLATIONS['ar'].keys())
        missing_in_ar = en_keys - ar_keys
        missing_in_en = ar_keys - en_keys
        assert not missing_in_ar, f"Keys missing in AR: {missing_in_ar}"
        assert not missing_in_en, f"Keys missing in EN: {missing_in_en}"
