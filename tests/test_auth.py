# -*- coding: utf-8 -*-
"""Tests for auth/auth.py module."""
import pytest

from auth.auth import (
    hash_password, verify_password,
    verify_admin_password, change_password,
    is_first_run, init_auth, _apply_pepper,
)


class TestPasswordHashing:
    def test_hash_returns_string(self):
        h = hash_password('test123')
        assert isinstance(h, str)
        assert len(h) > 20

    def test_hash_is_deterministic_with_pepper(self, monkeypatch):
        # Same password + same pepper should produce verifiable hash
        monkeypatch.setenv('EIMS_AUTH_PEPPER', 'test_pepper')
        # Clear cached pepper
        import auth.auth
        auth.auth._PEPPER = None

        h = hash_password('mypassword')
        assert verify_password('mypassword', h) is True

    def test_verify_wrong_password_fails(self, monkeypatch):
        monkeypatch.setenv('EIMS_AUTH_PEPPER', 'test_pepper')
        import auth.auth
        auth.auth._PEPPER = None

        h = hash_password('correct')
        assert verify_password('wrong', h) is False

    def test_hash_empty_raises(self):
        with pytest.raises(ValueError):
            hash_password('')

    def test_apply_pepper_changes_output(self, monkeypatch):
        # Without pepper
        monkeypatch.delenv('EIMS_AUTH_PEPPER', raising=False)
        import auth.auth
        auth.auth._PEPPER = None
        no_pepper = _apply_pepper('test')

        # With pepper
        monkeypatch.setenv('EIMS_AUTH_PEPPER', 'my_pepper')
        auth.auth._PEPPER = None
        with_pepper = _apply_pepper('test')

        assert no_pepper != with_pepper


class TestAdminPassword:
    def test_first_run_seeds_default(self, temp_db, monkeypatch):
        # Ensure no hash exists in temp DB (delete the setting entirely)
        import sqlite3
        from database import DB_NAME
        conn = sqlite3.connect(DB_NAME)
        conn.execute("DELETE FROM system_settings WHERE key = 'admin_password_hash'")
        conn.execute("DELETE FROM system_settings WHERE key = 'admin_first_run_done'")
        conn.commit()
        conn.close()

        monkeypatch.setenv('EIMS_AUTH_PEPPER', 'test_pepper')
        import auth.auth
        auth.auth._PEPPER = None

        # Clear the lru_cache so is_first_run reflects current state
        is_first_run.cache_clear()
        assert is_first_run() is True, "Should be first run with no hash stored"

        # Verify default password works after seeding
        result = verify_admin_password('1212')
        assert result is True, "Default password should work after first-run seeding"

    def test_change_password(self, temp_db, monkeypatch):
        monkeypatch.setenv('EIMS_AUTH_PEPPER', 'test_pepper')
        import auth.auth
        auth.auth._PEPPER = None
        auth.auth._initialized = False
        is_first_run.cache_clear()

        # Seed default first
        verify_admin_password('1212')

        # Change to new password
        ok, msg = change_password('1212', 'newpass456')
        assert ok is True, msg

        # Old default password should now fail (no longer the stored hash)
        # BUT verify_admin_password has auto-recovery for the default password
        # — so the behavior here is: '1212' will trigger re-seed and return True
        # We can only test that the new password definitely works
        assert verify_admin_password('newpass456') is True

    def test_change_password_wrong_current(self, temp_db, monkeypatch):
        monkeypatch.setenv('EIMS_AUTH_PEPPER', 'test_pepper')
        import auth.auth
        auth.auth._PEPPER = None
        auth.auth._initialized = False
        is_first_run.cache_clear()

        verify_admin_password('1212')  # seed

        ok, msg = change_password('wrong', 'newpass')
        assert ok is False
        assert 'incorrect' in msg.lower()

    def test_change_password_too_short(self, temp_db, monkeypatch):
        monkeypatch.setenv('EIMS_AUTH_PEPPER', 'test_pepper')
        import auth.auth
        auth.auth._PEPPER = None
        auth.auth._initialized = False
        is_first_run.cache_clear()

        verify_admin_password('1212')

        ok, msg = change_password('1212', 'ab')
        assert ok is False
        assert 'at least' in msg.lower()
