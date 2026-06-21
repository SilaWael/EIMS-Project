# -*- coding: utf-8 -*-
"""Tests for migrate_v1_to_v2.py classifier."""
import pytest

from migrate_v1_to_v2 import classify, extract_road, extract_segment


class TestClassifier:
    @pytest.mark.parametrize("sub_category,expected_discipline,expected_component", [
        # Earthworks
        ("Subgrade Layer 1", "EARTHWORKS", "EW_GEN_SUB1"),
        ("Subgrade Layer 2", "EARTHWORKS", "EW_GEN_SUB2"),
        ("Sidewalk Subgrade Layer 1", "EARTHWORKS", "EW_SW_SUB1"),
        ("Carriageway 1st Layer Subgrade", "EARTHWORKS", "EW_C_SUB1"),
        ("Service Road 1st Layer Subgrade", "EARTHWORKS", "EW_SV_SUB1"),
        ("Formation Level", "EARTHWORKS", "EW_GEN_FORM"),
        # Roadworks
        ("Road Base Layer", "ROADWORKS", "RW_C_BASE"),
        ("Asphalt Base Course Layer", "ROADWORKS", "RW_C_ASPHB"),
        ("Kerbstone Installation", "ROADWORKS", "RW_K_KERB"),
        # Wet Utilities
        ("Irrigation Pipe Laying", "WET_UTIL", "IR_MAIN"),
        ("Irrigation Main Line", "WET_UTIL", "IR_MAIN"),
        ("Potable Water Network", "WET_UTIL", "PW_PIPE"),
        ("Storm Water CB & Inlet Installation", "WET_UTIL", "SW_CB"),
        # Dry Utilities
        ("Installation of Telecom Network Conduit (2-Way)", "DRY_UTIL", "TEL_2W"),
        ("Installation of Telecom Network Conduit (4-Way)", "DRY_UTIL", "TEL_4W"),
        ("Installation of ADMCC Security Conduit", "DRY_UTIL", "ADMCC_COND"),
        ("FOC 110mm UPVC Pipe Installation", "DRY_UTIL", "FOC_PIPE"),
        ("MCC Pull Box Manhole Installation", "DRY_UTIL", "MCC_PULL"),
        ("Installation of Villa Entrance Electrical Duct", "DRY_UTIL", "LV_DUCT"),
        # Civil Structures
        ("Concrete Road Crossings", "STRUCTURES", "CR_CONC"),
        # Note: "Excavation & Formation for Telecom JRC-12 Manholes" matches Telecom
        # rule (it contains 'Telecom' + 'JRC-12') and is classified as TEL_MH_JRC12.
        # This is intentional — the structure is a telecom asset.
    ])
    def test_classify_known_patterns(self, sub_category, expected_discipline, expected_component):
        result = classify(sub_category)
        assert result is not None, f"Classifier returned None for: {sub_category}"
        assert result[0] == expected_discipline, f"Expected {expected_discipline}, got {result[0]}"
        assert result[2] == expected_component, f"Expected {expected_component}, got {result[2]}"

    def test_classify_empty_returns_none(self):
        assert classify('') is None
        assert classify(None) is None

    def test_classify_unknown_returns_none(self):
        assert classify('Totally Unknown Activity Type XYZ123') is None


class TestRoadExtraction:
    @pytest.mark.parametrize("location,expected_road", [
        ("Road-01 LHS Carriageway", "RD-01"),
        ("RD-05 RHS Sidewalk", "RD-05"),
        ("Road 1 (Service Road)", "RD-01"),
        ("RD-07 LHS", "RD-07"),
        ("Roundabout RA-01 Carriageway", "RA-01"),
        ("IPS Pump Room", "IPS"),
        ("Random location with no road", None),
    ])
    def test_extract_road(self, location, expected_road):
        road, _ = extract_road(location)
        assert road == expected_road


class TestSegmentExtraction:
    @pytest.mark.parametrize("location,expected_seg", [
        ("Road-01 LHS", "LHS"),
        ("RD-05 RHS Sidewalk", "RHS"),
        ("Road-01 Carriageway", "CARR"),
        ("RD-07 Sidewalk", "SW"),
        ("RD-01 Service Road", "SERV"),
        ("Random location", "NA"),
    ])
    def test_extract_segment(self, location, expected_seg):
        seg = extract_segment(location)
        assert seg == expected_seg
