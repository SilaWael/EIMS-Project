# -*- coding: utf-8 -*-
"""Tests for database.py module."""
import pytest
import sqlite3

from database import (
    init_db, save_setting, get_setting,
    normalize_date_to_db, format_date_to_display,
    save_record, delete_record, delete_records_bulk, reset_database,
    count_records, load_data,
    list_disciplines, list_systems, list_components,
)


class TestSettings:
    def test_save_and_get_setting(self, temp_db):
        save_setting('test_key', 'test_value')
        assert get_setting('test_key') == 'test_value'

    def test_get_setting_default(self, temp_db):
        assert get_setting('nonexistent', 'default') == 'default'

    def test_save_setting_overwrite(self, temp_db):
        save_setting('key1', 'v1')
        save_setting('key1', 'v2')
        assert get_setting('key1') == 'v2'


class TestDateHelpers:
    def test_normalize_yyyy_mm_dd(self):
        assert normalize_date_to_db('2026-06-15') == '2026-06-15'

    def test_normalize_dd_mm_yyyy(self):
        assert normalize_date_to_db('15-06-2026') == '2026-06-15'

    def test_normalize_slash_format(self):
        assert normalize_date_to_db('06/15/2026') == '2026-06-15'

    def test_normalize_float_str(self):
        assert normalize_date_to_db('2026-06-15.0') == '2026-06-15'

    def test_normalize_empty(self):
        assert normalize_date_to_db('') is None

    def test_normalize_invalid(self):
        assert normalize_date_to_db('not-a-date') == 'not-a-date'

    def test_format_to_display(self):
        assert format_date_to_display('2026-06-15') == '15-06-2026'

    def test_format_empty(self):
        assert format_date_to_display('') == ''


class TestReferenceData:
    def test_list_disciplines_en(self, temp_db):
        discs = list_disciplines('en')
        assert len(discs) == 6
        # First should be Earthworks
        assert 'Earthworks' in discs[0][2]

    def test_list_disciplines_ar(self, temp_db):
        discs = list_disciplines('ar')
        assert len(discs) == 6
        assert 'حفر' in discs[0][2]

    def test_list_systems_for_earthworks(self, temp_db):
        discs = list_disciplines('en')
        earthworks_id = discs[0][0]
        systems = list_systems(earthworks_id, 'en')
        assert len(systems) >= 4  # EW_GEN, EW_CARR, EW_SW, EW_SERV
        assert any('Formation' in s[2] for s in systems)

    def test_list_components_for_formation(self, temp_db):
        discs = list_disciplines('en')
        earthworks_id = discs[0][0]
        systems = list_systems(earthworks_id, 'en')
        gen_system_id = systems[0][0]  # EW_GEN
        components = list_components(gen_system_id, 'en')
        assert len(components) >= 4


class TestRecordCRUD:
    def test_save_record(self, temp_db, sample_record):
        assert count_records() == 0
        result = save_record(sample_record)
        assert result is True
        assert count_records() == 1

    def test_load_data_returns_dataframe(self, temp_db, sample_record):
        save_record(sample_record)
        df = load_data('en')
        assert len(df) == 1
        assert 'discipline_en' in df.columns
        assert df.iloc[0]['quantity'] == 120.5

    def test_load_data_arabic(self, temp_db, sample_record):
        save_record(sample_record)
        df = load_data('ar')
        assert 'discipline_ar' in df.columns
        assert 'حفر' in df.iloc[0]['discipline_ar']

    def test_delete_record(self, temp_db, sample_record):
        save_record(sample_record)
        assert count_records() == 1
        # Get the ID
        df = load_data('en')
        rec_id = df.iloc[0]['id']
        # Delete
        assert delete_record(rec_id) is True
        assert count_records() == 0

    def test_delete_records_bulk(self, temp_db, sample_record):
        # Insert 3 records
        for i in range(3):
            rec = sample_record.copy()
            rec['quantity'] = 100 + i
            save_record(rec)
        assert count_records() == 3

        df = load_data('en')
        ids = df['id'].tolist()
        deleted = delete_records_bulk(ids)
        assert deleted == 3
        assert count_records() == 0

    def test_reset_database(self, temp_db, sample_record):
        save_record(sample_record)
        save_record(sample_record)
        assert count_records() == 2
        reset_database()
        assert count_records() == 0


class TestDatabaseInitialization:
    def test_init_db_creates_tables(self, temp_db):
        conn = sqlite3.connect(temp_db)
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in c.fetchall()]
        conn.close()

        expected_tables = [
            'master_registry', 'system_settings',
            'ref_discipline', 'ref_system', 'ref_component',
            'ref_work_type', 'ref_stage', 'ref_road', 'ref_asset_segment',
        ]
        for tbl in expected_tables:
            assert tbl in tables, f"Table {tbl} should exist"

    def test_init_db_idempotent(self, temp_db):
        # Should not raise if called again
        init_db()
        init_db()
        assert count_records() == 0
