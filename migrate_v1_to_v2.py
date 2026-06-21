# -*- coding: utf-8 -*-
"""
EIMS Migration v1 -> v2
=======================
Migrates existing 219 records from the old flat classification
(category + sub_category + location) into the new hierarchical
classification (discipline_id + system_id + component_id + work_type_id
+ stage_id + road_id + asset_segment_id).

Strategy:
  1. Apply regex rules to old sub_category to derive (discipline, system, component, work_type, stage).
  2. Parse old location to extract road_id + asset_segment.
  3. Keep old fields intact (backward compatibility) — only fill new columns.
  4. Log unmatched records for manual review.

Run:  python3 migrate_v1_to_v2.py
"""
import re
import sqlite3
from database import get_conn, init_db
from classification_seed import seed_all


# ==============================================================================
#  MAPPING RULES — ordered, first match wins
#  Each rule: (regex_on_sub_category_lower, discipline_code, system_code,
#              component_code, work_type_code, stage_code_or_None)
# ==============================================================================
MAPPING_RULES = [
    # --- Earthworks: Sidewalk Subgrade Layer 1 ---
    (r"(sidewalk\s*subgrade\s*layer\s*1|sidewalk\s*1st\s*layer|footpath.*1st\s*layer|footpath.*subgrade\s*1)",
     "EARTHWORKS", "EW_SW", "EW_SW_SUB1", "COMP", "L1"),
    # --- Earthworks: Carriageway Subgrade Layer 1 ---
    (r"(carriageway\s*1st\s*layer\s*subgrade|carriageway\s*1st\s*layer)",
     "EARTHWORKS", "EW_CARR", "EW_C_SUB1", "COMP", "L1"),
    # --- Earthworks: Service Road Subgrade Layer 1 ---
    (r"(service\s*road\s*1st\s*layer\s*subgrade|service\s*road\s*1st\s*layer)",
     "EARTHWORKS", "EW_SERV", "EW_SV_SUB1", "COMP", "L1"),
    # --- Earthworks: Service Road Subgrade Layer 2 ---
    (r"(service\s*road\s*2nd\s*layer\s*subgrade|service\s*road\s*2nd\s*layer)",
     "EARTHWORKS", "EW_SERV", "EW_SV_SUB2", "COMP", "L2"),
    # --- Earthworks: Carriageway Subgrade Layer 2 ---
    (r"(carriageway\s*2nd\s*layer\s*subgrade|carriageway\s*2nd\s*layer)",
     "EARTHWORKS", "EW_CARR", "EW_C_SUB2", "COMP", "L2"),
    # --- Earthworks: Generic Subgrade Layer 1 ---
    (r"(subgrade\s*1st\s*layer|subgrade.*layer\s*1|1st\s*layer\s*subgrade)",
     "EARTHWORKS", "EW_GEN", "EW_GEN_SUB1", "COMP", "L1"),
    # --- Earthworks: Generic Subgrade Layer 2 ---
    (r"(subgrade\s*2nd\s*layer|subgrade.*layer\s*2|2nd\s*layer\s*subgrade)",
     "EARTHWORKS", "EW_GEN", "EW_GEN_SUB2", "COMP", "L2"),
    # --- Earthworks: Formation Level ---
    (r"(formation\s*level|formation\s*prep|formation\s*verification)",
     "EARTHWORKS", "EW_GEN", "EW_GEN_FORM", "FORM", "VERIFY"),
    (r"(sidewalk.*formation|sidewalk\s*way\s*formation|footpath\s*formation)",
     "EARTHWORKS", "EW_SW", "EW_SW_FORM", "FORM", None),
    (r"(carriageway\s*formation)",
     "EARTHWORKS", "EW_CARR", "EW_C_FORM", "FORM", None),
    (r"(service\s*road\s*formation)",
     "EARTHWORKS", "EW_SERV", "EW_SV_FORM", "FORM", None),
    (r"(road\s*formation)",
     "EARTHWORKS", "EW_GEN", "EW_GEN_FORM", "FORM", None),

    # --- Roadworks: Base & Asphalt ---
    # IMPORTANT: Check "asphalt" patterns BEFORE "road base" to avoid false match
    (r"(asphalt.*base)",
     "ROADWORKS", "RW_CARR", "RW_C_ASPHB", "LAY", None),
    (r"(asphalt.*wearing)",
     "ROADWORKS", "RW_CARR", "RW_C_ASPHW", "LAY", None),
    (r"(road\s*base\s*layer|base\s*course)",
     "ROADWORKS", "RW_CARR", "RW_C_BASE", "LAY", "BASE"),
    (r"(walkway\s*construction|sidewalk.*pav)",
     "ROADWORKS", "RW_SW", "RW_SW_PAVE", "CONSTR", None),
    (r"(walkway)",
     "ROADWORKS", "RW_SW", "RW_SW_WALK", "CONSTR", None),

    # --- Roadworks: Kerb ---
    (r"(kerb)",
     "ROADWORKS", "RW_KERB", "RW_K_KERB", "INST", None),

    # --- Wet Utilities: Potable Water ---
    (r"(potable\s*water)",
     "WET_UTIL", "WET_PW", "PW_PIPE", "LAY", None),

    # --- Wet Utilities: Irrigation ---
    (r"(irrigation.*main.*line|main\s*line.*irrigation)",
     "WET_UTIL", "WET_IR", "IR_MAIN", "LAY", None),
    (r"(irrigation.*sub\s*main|submain|sub-main)",
     "WET_UTIL", "WET_IR", "IR_SUB", "LAY", None),
    (r"(irrigation.*lateral|lateral\s*.*\s*drip|lateral\s*&\s*drip)",
     "WET_UTIL", "WET_IR", "IR_LAT", "LAY", None),
    (r"(irrigation.*drip)",
     "WET_UTIL", "WET_IR", "IR_DRIP", "LAY", None),
    (r"(irrigation.*connection|connection\s*line)",
     "WET_UTIL", "WET_IR", "IR_CONN", "LAY", None),
    (r"(irrigation.*conduit|conduit.*irrigation)",
     "WET_UTIL", "WET_IR", "IR_CONDUIT", "LAY", None),
    (r"(irrigation\s*pipe\s*laying|irrigation\s*installation)",
     "WET_UTIL", "WET_IR", "IR_MAIN", "LAY", None),
    (r"(irrigation\s*pump\s*station)",
     "STRUCTURES", "ST_PUMP", "PS_ROOM", "CONSTR", None),

    # --- Wet Utilities: Storm Water ---
    (r"(storm\s*water|catch\s*basin|storm.*inlet|storm.*cb)",
     "WET_UTIL", "WET_SW", "SW_CB", "INST", None),

    # --- Wet Utilities: Trench / Conduit Jointing (default to irrigation if context wet) ---
    (r"(trench\s*excavation)",
     "WET_UTIL", "WET_IR", "IR_MAIN", "EXC", None),
    (r"(conduit\s*jointing)",
     "WET_UTIL", "WET_IR", "IR_MAIN", "JOINT", None),

    # --- Wet Utilities: Sewer / Surveying existing sewer ---
    (r"(sewer.*manhole|existing\s*sewer|sewer\s*survey)",
     "WET_UTIL", "WET_FOUL", "FOUL_MH", "SURV", None),

    # --- Wet Utilities: JRC Inspection (could be telecom or wet — default telecom) ---
    # handled below for dry

    # --- Dry Utilities: Telecom ---
    (r"(telecom.*2.?way|2.?way.*conduit)",
     "DRY_UTIL", "DRY_TEL", "TEL_2W", "LAY", None),
    (r"(telecom.*4.?way|4.?way.*conduit)",
     "DRY_UTIL", "DRY_TEL", "TEL_4W", "LAY", None),
    (r"(telecom.*upvc\s*sleeve|upvc.*sleeve.*telecom)",
     "DRY_UTIL", "DRY_TEL", "TEL_SLEEVE", "LAY", None),
    (r"(telecom.*jrc.?12|jrc.?12.*manhole)",
     "DRY_UTIL", "DRY_TEL", "TEL_MH_JRC12", "EXC", None),
    (r"(telecom.*pull\s*box|pull\s*box.*telecom)",
     "DRY_UTIL", "DRY_TEL", "TEL_PULL", "EXC", None),
    (r"(telecom.*frame|frame.*cover.*telecom|jrc.?12.*frame)",
     "DRY_UTIL", "DRY_TEL", "TEL_FC", "INST", None),
    (r"(telecom.*trench|trench.*telecom)",
     "DRY_UTIL", "DRY_TEL", "TEL_2W", "EXC", None),
    (r"(telecom.*manhole.*excavation|excavation.*blinding.*telecom)",
     "DRY_UTIL", "DRY_TEL", "TEL_MH_JRC12", "EXC", None),
    (r"(telecom.*pull.*box.*cover|pull.*box.*cover)",
     "DRY_UTIL", "DRY_TEL", "TEL_PULL", "INST", None),
    (r"(telecom\s*network\s*conduit)",
     "DRY_UTIL", "DRY_TEL", "TEL_2W", "LAY", None),
    (r"(rd\s*\d.*conduite|conduite\s*\d+mm)",
     "DRY_UTIL", "DRY_TEL", "TEL_2W", "LAY", None),

    # --- Dry Utilities: ADMCC / Security ---
    (r"(admcc)",
     "DRY_UTIL", "DRY_ADMCC", "ADMCC_COND", "LAY", None),
    (r"(service\s*turret)",
     "DRY_UTIL", "DRY_ADMCC", "ADMCC_TURR", "EXC", None),
    (r"(security)",
     "DRY_UTIL", "DRY_ADMCC", "ADMCC_COND", "LAY", None),

    # --- Dry Utilities: FOC (Fiber Optic) ---
    (r"(foc|fiber\s*optic|fibre)",
     "DRY_UTIL", "DRY_FOC", "FOC_PIPE", "LAY", None),
    (r"(foc.*trench|trench.*foc)",
     "DRY_UTIL", "DRY_FOC", "FOC_TRENCH", "EXC", None),

    # --- Dry Utilities: MCC ---
    (r"(mcc.*pull.*box|pull.*box.*mcc)",
     "DRY_UTIL", "DRY_MCC", "MCC_PULL", "INST", None),
    (r"(mcc.*pull.*box.*excavation|mcc.*excavation|excavation.*mcc)",
     "DRY_UTIL", "DRY_MCC", "MCC_PULL", "EXC", None),
    (r"(mcc.*duct|duct.*mcc|mcc.*encasement)",
     "DRY_UTIL", "DRY_MCC", "MCC_DUCT", "ENCASE", None),

    # --- Dry Utilities: LV Electrical ---
    (r"(villa\s*entrance.*electrical|electrical.*duct.*entrance|entrance\s*electrical)",
     "DRY_UTIL", "DRY_LV", "LV_DUCT", "LAY", None),
    (r"(electrical\s*duct.*vertical|vertical.*electrical)",
     "DRY_UTIL", "DRY_LV", "LV_DUCT", "INST", None),
    (r"(electrical\s*duct.*crossing|electrical.*road\s*crossing)",
     "DRY_UTIL", "DRY_LV", "LV_DUCT", "LAY", None),
    (r"(electrical\s*duct)",
     "DRY_UTIL", "DRY_LV", "LV_DUCT", "LAY", None),
    (r"(electrical\s*room)",
     "STRUCTURES", "ST_ELEC", "ER_ROOM", "CONSTR", None),
    (r"(feeder\s*pillar)",
     "STRUCTURES", "ST_FOUND", "FD_EXC", "EXC", None),
    (r"(street\s*poles?|street\s*light\s*pole)",
     "DRY_UTIL", "DRY_LIGHT", "LT_POLE", "INST", None),
    (r"(lighting)",
     "DRY_UTIL", "DRY_LIGHT", "LT_POLE", "INST", None),

    # --- Civil Structures: Crossings ---
    (r"(concrete\s*road\s*crossing|road\s*crossing)",
     "STRUCTURES", "ST_CROSS", "CR_CONC", "CONSTR", None),
    (r"(upvc\s*sleeve.*crossing|sleeve.*concrete\s*casing|upvc.*concrete\s*incasing)",
     "STRUCTURES", "ST_CROSS", "CR_UPVC", "ENCASE", None),
    (r"(concrete\s*encasement|concrete\s*casing|concrete\s*incasing)",
     "STRUCTURES", "ST_CROSS", "CR_UPVC", "ENCASE", None),

    # --- Civil Structures: Manholes & Chambers (general) ---
    (r"(jrc.?12.*excavation|excavation.*formation.*jrc|excavation.*blinding.*jrc)",
     "STRUCTURES", "ST_MH", "MH_JRC12", "EXC", None),
    (r"(jrc.?12.*frame|frame.*cover.*jrc|jrc.*inspection)",
     "STRUCTURES", "ST_MH", "MH_JRC12", "INST", None),
    (r"(pull\s*box\s*chamber|pull\s*box.*excavation|excavation.*blinding.*pull\s*box|pull\s*box.*cover)",
     "STRUCTURES", "ST_MH", "MH_PULLBOX", "EXC", None),
    (r"(sewer\s*manhole|existing\s*sewer\s*manhole)",
     "WET_UTIL", "WET_FOUL", "FOUL_MH", "SURV", None),

    # --- Dry Utilities: Cable Conduit (catch-all) ---
    (r"(cable\s*conduit|32mm\s*cable)",
     "DRY_UTIL", "DRY_LV", "LV_DUCT", "LAY", None),

    # --- Wet Utilities: Irrigation parallel line (RD-specific drip laterals) ---
    (r"(parallel\s*line)",
     "WET_UTIL", "WET_IR", "IR_MAIN", "LAY", None),

    # --- Default fallback (unclassified) ---
    # None — will be flagged for manual review
]

# Smart component override: if rule says system None, derive system from component's discipline
# This is handled in apply_rule below.


# ==============================================================================
#  ROAD & SEGMENT EXTRACTION FROM LOCATION
# ==============================================================================
ROAD_PATTERNS = [
    # (regex, road_code)
    (r"\bRD[\s\-]*0?1\b(?!0)",        "RD-01"),
    (r"\bRD[\s\-]*0?2\b(?!0)",        "RD-02"),
    (r"\bRD[\s\-]*0?4\b(?!0)",        "RD-04"),
    (r"\bRD[\s\-]*0?5\b(?!0)",        "RD-05"),
    (r"\bRD[\s\-]*0?6\b(?!0)",        "RD-06"),
    (r"\bRD[\s\-]*0?7\b(?!0)",        "RD-07"),
    (r"\bRD[\s\-]*0?8\b(?!0)",        "RD-08"),
    (r"\bRD[\s\-]*0?9\b(?!0)",        "RD-09"),
    (r"\bRoad[\s\-]*0?1\b(?!0)",      "RD-01"),
    (r"\bRoad[\s\-]*0?2\b(?!0)",      "RD-02"),
    (r"\bRoad[\s\-]*0?4\b(?!0)",      "RD-04"),
    (r"\bRoad[\s\-]*0?5\b(?!0)",      "RD-05"),
    (r"\bRoad[\s\-]*0?6\b(?!0)",      "RD-06"),
    (r"\bRoad[\s\-]*0?7\b(?!0)",      "RD-07"),
    (r"\bRoad[\s\-]*0?8\b(?!0)",      "RD-08"),
    (r"\bRoad[\s\-]*0?9\b(?!0)",      "RD-09"),
    (r"\bRA[\s\-]*0?1\b(?!0)",        "RA-01"),
    (r"\bRA[\s\-]*0?2\b(?!0)",        "RA-02"),
    (r"\bRoundabout\s*RA[\s\-]*0?1\b","RA-01"),
    (r"\bRoundabout\s*RA[\s\-]*0?2\b","RA-02"),
    (r"\bIPS\b|\bIPS\s*Pump\b|\bIPS\s*Electrical\b", "IPS"),
]

SEGMENT_PATTERNS = [
    (r"\bLHS\b",                                "LHS"),
    (r"\bRHS\b",                                "RHS"),
    (r"\bLHS\s*&\s*RHS\b|\bRHS\s*&\s*LHS\b|\bboth\s*sides?\b", "BOTH"),
    (r"\bcarriageway\b",                        "CARR"),
    (r"\bsidewalk\b|\bfootpath\b|\bwalkway\b",  "SW"),
    (r"\bservice\s*road\b",                     "SERV"),
    (r"\bwalkway\b",                            "WALK"),
]


def extract_road(location):
    if not location:
        return None, None
    loc = str(location)
    # Try patterns in order
    for pat, code in ROAD_PATTERNS:
        if re.search(pat, loc, re.IGNORECASE):
            return code, loc
    # No road found
    return None, loc


def extract_segment(location):
    if not location:
        return "NA"
    loc = str(location)
    for pat, code in SEGMENT_PATTERNS:
        if re.search(pat, loc, re.IGNORECASE):
            return code
    return "NA"


# ==============================================================================
#  CLASSIFIER
# ==============================================================================
def classify(sub_category):
    """Returns (discipline_code, system_code, component_code, work_type_code, stage_code) or None."""
    if not sub_category:
        return None
    s = str(sub_category).lower().strip()

    for regex, d_code, s_code, c_code, wt_code, st_code in MAPPING_RULES:
        if re.search(regex, s, re.IGNORECASE):
            # If s_code is None, infer from component (find a system that contains this component)
            if not s_code and c_code:
                # Find any system that has this component — use first one (component codes are unique)
                conn = get_conn()
                row = conn.execute(
                    "SELECT system_id FROM ref_component WHERE code=?", (c_code,)
                ).fetchone()
                conn.close()
                if row:
                    s_code = conn.execute  # placeholder, will use the row below
                    # Actually we need to fetch the system code:
                    conn = get_conn()
                    sys_row = conn.execute(
                        "SELECT s.code FROM ref_system s JOIN ref_component c ON c.system_id=s.id WHERE c.code=?",
                        (c_code,)
                    ).fetchone()
                    conn.close()
                    if sys_row:
                        s_code = sys_row[0]
            return (d_code, s_code, c_code, wt_code, st_code)

    return None


def get_ref_id(table, code):
    """Returns the id from a reference table by code, or None."""
    if not code:
        return None
    conn = get_conn()
    row = conn.execute(f"SELECT id FROM {table} WHERE code=?", (code,)).fetchone()
    conn.close()
    return row[0] if row else None


def get_component_id_by_code(code):
    if not code:
        return None
    conn = get_conn()
    row = conn.execute("SELECT id FROM ref_component WHERE code=?", (code,)).fetchone()
    conn.close()
    return row[0] if row else None


# ==============================================================================
#  MIGRATION MAIN
# ==============================================================================
def migrate():
    # Step 1: ensure schema + seed
    print("[1/4] Initializing schema and seeding reference data...")
    seed_all()

    print("[2/4] Loading existing records...")
    conn = get_conn()
    rows = conn.execute("""
        SELECT id, sub_category, location
        FROM master_registry
    """).fetchall()
    print(f"      Found {len(rows)} records to migrate.")

    print("[3/4] Classifying and updating each record...")

    matched = 0
    unmatched = []
    road_matched = 0
    seg_matched = 0

    for rec_id, sub_cat, location in rows:
        # Classify
        cls = classify(sub_cat)
        discipline_id = None
        system_id = None
        component_id = None
        work_type_id = None
        stage_id = None

        if cls:
            d_code, s_code, c_code, wt_code, st_code = cls
            discipline_id = get_ref_id("ref_discipline", d_code)
            system_id = get_ref_id("ref_system", s_code) if s_code else None
            component_id = get_component_id_by_code(c_code) if c_code else None
            work_type_id = get_ref_id("ref_work_type", wt_code) if wt_code else None
            stage_id = get_ref_id("ref_stage", st_code) if st_code else None
            matched += 1
        else:
            unmatched.append((rec_id, sub_cat, location))

        # Extract road and segment
        road_code, _ = extract_road(location)
        road_id = get_ref_id("ref_road", road_code) if road_code else None
        if road_id:
            road_matched += 1

        seg_code = extract_segment(location)
        seg_id = get_ref_id("ref_asset_segment", seg_code)
        if seg_id and seg_code != "NA":
            seg_matched += 1

        # Update
        conn.execute("""
            UPDATE master_registry
            SET discipline_id=?, system_id=?, component_id=?, work_type_id=?, stage_id=?,
                road_id=?, asset_segment_id=?
            WHERE id=?
        """, (discipline_id, system_id, component_id, work_type_id, stage_id,
              road_id, seg_id, rec_id))

    conn.commit()
    conn.close()

    print("[4/4] Migration complete.")
    print(f"\n=== MIGRATION REPORT ===")
    print(f"Total records:        {len(rows)}")
    print(f"Classification:       {matched}/{len(rows)} matched ({matched*100//len(rows) if rows else 0}%)")
    print(f"  Unmatched:          {len(unmatched)}")
    print(f"Road extracted:       {road_matched}/{len(rows)}")
    print(f"Segment extracted:    {seg_matched}/{len(rows)}")

    if unmatched:
        print(f"\n--- UNMATCHED RECORDS (need manual review) ---")
        for rec_id, sub_cat, location in unmatched:
            print(f"  ID {rec_id}: sub='{sub_cat}' | loc='{location}'")

    return {
        "total": len(rows),
        "matched": matched,
        "unmatched": len(unmatched),
        "road_matched": road_matched,
        "seg_matched": seg_matched,
        "unmatched_records": unmatched,
    }


if __name__ == "__main__":
    result = migrate()
    print("\n[DONE] Migration finished.")
