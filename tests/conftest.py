# -*- coding: utf-8 -*-
"""
Pytest configuration & fixtures for EIMS tests.

Run all tests:
    py -m pytest tests/ -v

Run a specific test file:
    py -m pytest tests/test_database.py -v
"""
import os
import sys
import sqlite3
import tempfile
import shutil
import pytest

# Ensure project root is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


@pytest.fixture(scope="function")
def temp_db(monkeypatch, tmp_path):
    """Provide a temporary database file for isolated tests.

    This fixture:
      - Creates a fresh eims.db in a temp directory
      - Patches DB_NAME so all modules use the temp DB
      - Seeds the reference data (classification)
      - Yields the temp path
      - Cleans up after the test
    """
    temp_dir = tmp_path / "eims_test"
    temp_dir.mkdir()
    temp_db_path = str(temp_dir / "eims_test.db")

    # Patch DB_NAME everywhere
    import database
    monkeypatch.setattr(database, 'DB_NAME', temp_db_path)

    # Also patch in modules that imported DB_NAME by value
    # (none currently do — they all call get_conn() which uses the patched DB_NAME)

    # Initialize schema
    database.init_db()

    # Seed reference data
    from classification_seed import seed_all
    seed_all()

    yield temp_db_path

    # Cleanup
    try:
        os.remove(temp_db_path)
    except Exception:
        pass


@pytest.fixture
def sample_record():
    """Returns a sample record dict for testing save_record."""
    return {
        'report_date': '15-06-2026',
        'category': 'Road Works',
        'sub_category': 'Subgrade Layer 1',
        'location': 'Road-01 LHS',
        'quantity': 120.5,
        'unit': 'm',
        'status': 'Pass',
        'remarks': 'Approved within tolerance',
        'detailed_levels': [
            {'point': '0+000', 'design': 10.5, 'as_built': 10.48, 'diff': -0.02, 'status': 'Pass'}
        ],
        'discipline_id': 1,  # Earthworks
        'system_id': 5,      # EW_GEN
        'component_id': 5,   # EW_GEN_SUB1
        'work_type_id': 6,   # Compaction
        'stage_id': 1,       # Layer 1
        'road_id': 1,        # RD-01
        'asset_segment_id': 1,  # LHS
        'stationing': '0+000 to 0+120',
        'activity_detail': '- Subgrade Layer 1 audit\n- 6 points verified',
    }
