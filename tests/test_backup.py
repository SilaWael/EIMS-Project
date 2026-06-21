# -*- coding: utf-8 -*-
"""Tests for core/backup.py module."""
import os
import sqlite3
import pytest

from core.backup import create_backup, list_backups, delete_backup, BACKUP_DIR


class TestBackup:
    def test_create_backup(self, temp_db, monkeypatch, tmp_path):
        # Patch BACKUP_DIR to use tmp
        import core.backup
        monkeypatch.setattr(core.backup, 'BACKUP_DIR', str(tmp_path / 'backups'))

        # Insert a record first
        from database import save_setting
        save_setting('test', 'value')

        result = create_backup('test_run')
        assert result is not None
        assert os.path.exists(result)

    def test_list_backups_empty(self, temp_db, monkeypatch, tmp_path):
        import core.backup
        monkeypatch.setattr(core.backup, 'BACKUP_DIR', str(tmp_path / 'empty_backups'))

        backups = list_backups()
        assert backups == []

    def test_list_backups_after_create(self, temp_db, monkeypatch, tmp_path):
        import core.backup
        import time
        backup_dir = str(tmp_path / 'backups')
        monkeypatch.setattr(core.backup, 'BACKUP_DIR', backup_dir)

        from database import save_setting
        save_setting('test', 'value')

        create_backup('test1')
        # Sleep briefly to ensure different mtime
        time.sleep(0.05)
        create_backup('test2')

        backups = list_backups()
        assert len(backups) == 2
        # Both should be in the list (order may vary if created in same second)
        names = [b['name'] for b in backups]
        assert any('test1' in n for n in names)
        assert any('test2' in n for n in names)

    def test_delete_backup(self, temp_db, monkeypatch, tmp_path):
        import core.backup
        monkeypatch.setattr(core.backup, 'BACKUP_DIR', str(tmp_path / 'backups'))

        from database import save_setting
        save_setting('test', 'value')
        path = create_backup('to_delete')

        assert os.path.exists(path)
        assert delete_backup(path) is True
        assert not os.path.exists(path)

    def test_delete_nonexistent_backup(self, temp_db):
        assert delete_backup('/nonexistent/path.db') is False
