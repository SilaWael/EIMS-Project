# -*- coding: utf-8 -*-
"""Tests for core/exporter.py and ui/charts.py modules."""
import pytest
import pandas as pd

from database import save_record, load_data
from core.exporter import export_to_excel, export_to_csv, _build_master_sheet, _build_discipline_summary
from core.pdf_report import generate_progress_report
from ui.charts import (
    chart_cumulative_timeseries, chart_distribution_donut,
    chart_roads_heatmap, chart_monthly_stacked, chart_weekly_activity,
    compute_kpis,
)


@pytest.fixture
def populated_db(temp_db, sample_record):
    """Insert a few records for testing."""
    for i in range(5):
        rec = sample_record.copy()
        rec['quantity'] = 100 + i * 10
        save_record(rec)
    return temp_db


class TestExcelExport:
    def test_export_to_excel_returns_bytes(self, populated_db):
        df = load_data('en')
        result = export_to_excel(df, 'en')
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_export_to_excel_arabic(self, populated_db):
        df = load_data('ar')
        result = export_to_excel(df, 'ar')
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_export_to_excel_empty_returns_empty(self, temp_db):
        df = load_data('en')
        assert df.empty
        result = export_to_excel(df, 'en')
        assert result == b''

    def test_build_master_sheet(self, populated_db):
        df = load_data('en')
        master = _build_master_sheet(df, 'en')
        assert len(master) == 5
        assert 'ID' in master.columns
        assert 'Discipline' in master.columns

    def test_build_discipline_summary(self, populated_db):
        df = load_data('en')
        summary = _build_discipline_summary(df, 'en')
        assert len(summary) > 0
        assert 'Records Count' in summary.columns
        assert 'Total Quantity (m)' in summary.columns


class TestCSVExport:
    def test_export_to_csv(self, populated_db):
        df = load_data('en')
        result = export_to_csv(df, 'en')
        assert isinstance(result, bytes)
        assert b'ID' in result
        assert b'Discipline' in result


class TestPDFReport:
    def test_generate_pdf(self, populated_db):
        df = load_data('en')
        kpis = compute_kpis(df, 'en')
        pdf = generate_progress_report(df, kpis, lang='en')
        assert isinstance(pdf, bytes)
        assert len(pdf) > 0
        # PDF magic bytes
        assert pdf[:4] == b'%PDF'

    def test_generate_pdf_arabic(self, populated_db):
        df = load_data('ar')
        kpis = compute_kpis(df, 'ar')
        pdf = generate_progress_report(df, kpis, lang='ar')
        assert isinstance(pdf, bytes)
        assert pdf[:4] == b'%PDF'

    def test_generate_pdf_empty(self, temp_db):
        df = load_data('en')
        kpis = compute_kpis(df, 'en')
        pdf = generate_progress_report(df, kpis, lang='en')
        assert pdf == b''


class TestCharts:
    def test_compute_kpis(self, populated_db):
        df = load_data('en')
        kpis = compute_kpis(df, 'en')
        assert kpis['total_records'] == 5
        assert kpis['total_qty'] == 600  # 100+110+120+130+140
        assert kpis['unique_roads'] >= 0

    def test_chart_cumulative_timeseries(self, populated_db):
        df = load_data('en')
        fig = chart_cumulative_timeseries(df, 'en')
        assert fig is not None

    def test_chart_distribution_donut(self, populated_db):
        df = load_data('en')
        fig = chart_distribution_donut(df, 'en')
        assert fig is not None

    def test_chart_monthly_stacked(self, populated_db):
        df = load_data('en')
        fig = chart_monthly_stacked(df, 'en')
        assert fig is not None

    def test_chart_weekly_activity(self, populated_db):
        df = load_data('en')
        fig = chart_weekly_activity(df, 'en')
        assert fig is not None

    def test_chart_roads_heatmap(self, populated_db):
        df = load_data('en')
        fig = chart_roads_heatmap(df, 'en')
        assert fig is not None

    def test_charts_empty_db(self, temp_db):
        df = load_data('en')
        assert df.empty
        assert chart_cumulative_timeseries(df, 'en') is None
        assert chart_distribution_donut(df, 'en') is None
