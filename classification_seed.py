# -*- coding: utf-8 -*-
"""
EIMS Classification Seed Data v2
================================
Hierarchical classification for infrastructure projects:
  L1 Discipline -> L2 System -> L3 Component
  L4 Work Type   -> L5 Stage
  + Roads and Asset Segments

All entries are bilingual (EN + AR).
"""
import sqlite3
from database import get_conn, init_db


# ==============================================================================
#  L1: DISCIPLINES (6)
# ==============================================================================
DISCIPLINES = [
    # (code, name_en, name_ar, sort_order)
    ("EARTHWORKS", "Earthworks & Formation",        "أعمال الحفر والتشكيل",        1),
    ("ROADWORKS",  "Roadworks & Paving",            "أعمال الطرق والرصف",          2),
    ("WET_UTIL",   "Wet Utilities (Hydraulic)",     "الشبكات الرطبة (الهيدروليكية)",3),
    ("DRY_UTIL",   "Dry Utilities (Electrical/Comm)","الشبكات الجافة (كهرباء/اتصالات)",4),
    ("STRUCTURES", "Civil Structures",              "المنشآت المدنية",             5),
    ("LANDSCAPE",  "Landscape & Soft Works",        "أعمال التنسيق والزراعة",      6),
]

# ==============================================================================
#  L2: SYSTEMS (grouped by discipline)
# ==============================================================================
SYSTEMS = [
    # (discipline_code, code, name_en, name_ar, sort_order)
    # --- Earthworks & Formation ---
    ("EARTHWORKS", "EW_GEN",   "General Formation",        "تشكيل عام",                  1),
    ("EARTHWORKS", "EW_CARR",  "Carriageway Formation",    "تشكيل ساحة الطريق",          2),
    ("EARTHWORKS", "EW_SW",    "Sidewalk Formation",       "تشكيل الرصيف",               3),
    ("EARTHWORKS", "EW_SERV",  "Service Road Formation",   "تشكيل الطريق الخدمي",        4),

    # --- Roadworks & Paving ---
    ("ROADWORKS",  "RW_CARR",  "Carriageway",              "ساحة الطريق",                1),
    ("ROADWORKS",  "RW_SW",    "Sidewalk",                 "رصيف المشاة",                2),
    ("ROADWORKS",  "RW_SERV",  "Service Road",             "طريق خدمي",                  3),
    ("ROADWORKS",  "RW_RA",    "Roundabout",               "دوار",                       4),
    ("ROADWORKS",  "RW_KERB",  "Kerb & Channel",           "الأرصفة والقنوات",           5),

    # --- Wet Utilities ---
    ("WET_UTIL",   "WET_PW",   "Potable Water",            "مياه الشرب",                 1),
    ("WET_UTIL",   "WET_IR",   "Irrigation",               "الري",                       2),
    ("WET_UTIL",   "WET_SW",   "Storm Water Drainage",     "تصريف مياه الأمطار",         3),
    ("WET_UTIL",   "WET_FOUL", "Foul Sewer",               "شبكة الصرف الصحي",           4),

    # --- Dry Utilities ---
    ("DRY_UTIL",   "DRY_LV",   "LV Electrical",            "كهرباء منخفضة الجهد",        1),
    ("DRY_UTIL",   "DRY_LIGHT","Street Lighting",          "إنارة الشوارع",              2),
    ("DRY_UTIL",   "DRY_TEL",  "Telecom",                  "اتصالات",                    3),
    ("DRY_UTIL",   "DRY_ADMCC","ADMCC / Security",         "ADMCC / أمن",                4),
    ("DRY_UTIL",   "DRY_FOC",  "FOC (Fiber Optic)",        "كابل الألياف البصرية",       5),
    ("DRY_UTIL",   "DRY_MCC",  "MCC (Motor Control)",      "لوحات تحكم المحركات",        6),

    # --- Civil Structures ---
    ("STRUCTURES", "ST_MH",    "Manholes & Chambers",      "بيارات وغرف",                1),
    ("STRUCTURES", "ST_CROSS", "Crossings",                "تقاطعات",                    2),
    ("STRUCTURES", "ST_PUMP",  "Pump Stations",            "محطات ضخ",                   3),
    ("STRUCTURES", "ST_ELEC",  "Electrical Rooms",         "غرف كهرباء",                 4),
    ("STRUCTURES", "ST_FOUND", "Foundations",              "أساسات",                     5),

    # --- Landscape & Soft Works ---
    ("LANDSCAPE",  "LS_SOFT",  "Soft Landscape",           "تنسيق ناعم (زراعة)",         1),
    ("LANDSCAPE",  "LS_HARD",  "Hardscape",                "تنسيق صلب",                  2),
    ("LANDSCAPE",  "LS_PUMP",  "Irrigation Pumps",         "مضخات الري",                 3),
]

# ==============================================================================
#  L3: COMPONENTS (grouped by system code)
# ==============================================================================
COMPONENTS = [
    # (system_code, code, name_en, name_ar, sort_order)
    # --- Earthworks ---
    ("EW_GEN",   "EW_GEN_FORM", "Formation Level",              "منسوب التشكيل",                1),
    ("EW_GEN",   "EW_GEN_EXC",  "General Excavation",           "حفر عام",                      2),
    ("EW_GEN",   "EW_GEN_BACK", "Backfill",                     "ردم",                          3),
    ("EW_GEN",   "EW_GEN_COMP", "Compaction",                   "دمك",                          4),
    ("EW_GEN",   "EW_GEN_SUB1", "Subgrade (Layer 1)",           "الطبقة التحتية (الطبقة 1)",    5),
    ("EW_GEN",   "EW_GEN_SUB2", "Subgrade (Layer 2)",           "الطبقة التحتية (الطبقة 2)",    6),
    ("EW_CARR",  "EW_C_FORM",   "Carriageway Formation Level",  "منسوب تشكيل الساحة",           1),
    ("EW_CARR",  "EW_C_SUB1",   "Carriageway Subgrade L1",      "طبقة ساحة الطريق 1",           2),
    ("EW_CARR",  "EW_C_SUB2",   "Carriageway Subgrade L2",      "طبقة ساحة الطريق 2",           3),
    ("EW_SW",    "EW_SW_FORM",  "Sidewalk Formation Level",     "منسوب تشكيل الرصيف",           1),
    ("EW_SW",    "EW_SW_SUB1",  "Sidewalk Subgrade L1",         "طبقة الرصيف 1",                2),
    ("EW_SERV",  "EW_SV_FORM",  "Service Road Formation",       "تشكيل الطريق الخدمي",          1),
    ("EW_SERV",  "EW_SV_SUB1",  "Service Road Subgrade L1",     "طبقة الطريق الخدمي 1",         2),
    ("EW_SERV",  "EW_SV_SUB2",  "Service Road Subgrade L2",     "طبقة الطريق الخدمي 2",         3),

    # --- Roadworks ---
    ("RW_CARR",  "RW_C_BASE",   "Base Course",                  "طبقة الأساس",                  1),
    ("RW_CARR",  "RW_C_ASPHB",  "Asphalt Binder Course",        "طبقة الإسفلت الرابط",          2),
    ("RW_CARR",  "RW_C_ASPHW",  "Asphalt Wearing Course",       "طبقة الإسفلت السطحية",         3),
    ("RW_SW",    "RW_SW_PAVE",  "Sidewalk Paving",              "رصف الرصيف",                   1),
    ("RW_SW",    "RW_SW_WALK",  "Walkway",                      "ممر مشاة",                     2),
    ("RW_SERV",  "RW_SV_PAVE",  "Service Road Paving",          "رصف الطريق الخدمي",            1),
    ("RW_RA",    "RW_RA_PAVE",  "Roundabout Paving",            "رصف الدوار",                   1),
    ("RW_KERB",  "RW_K_KERB",   "Precast Kerbstone",            "رصف حجري مسبق الصب",           1),
    ("RW_KERB",  "RW_K_CHN",    "Channel",                      "قناة تصريف",                   2),

    # --- Wet Utilities ---
    ("WET_PW",   "PW_PIPE",     "PW Pipe",                      "أنبوب مياه شرب",               1),
    ("WET_PW",   "PW_VALVE",    "PW Valve/Fitting",             "صمام/توصيلة مياه شرب",         2),
    ("WET_PW",   "PW_HYDR",     "PW Hydrant",                   "حريق مياه شرب",                3),
    ("WET_IR",   "IR_MAIN",     "Irrigation Main Line",         "الخط الرئيسي للري",            1),
    ("WET_IR",   "IR_SUB",      "Irrigation Sub-main",          "خط فرعي رئيسي للري",           2),
    ("WET_IR",   "IR_LAT",      "Irrigation Lateral",           "خط ري جانبي",                  3),
    ("WET_IR",   "IR_DRIP",     "Irrigation Drip Line",         "خط الري بالتنقيط",             4),
    ("WET_IR",   "IR_CONN",     "Irrigation Connection Line",   "خط وصل الري",                  5),
    ("WET_IR",   "IR_CONDUIT",  "Irrigation Conduit",           "قناة ري",                      6),
    ("WET_SW",   "SW_PIPE",     "Storm Water Pipe",             "أنبوب تصريف أمطار",            1),
    ("WET_SW",   "SW_CB",       "Catch Basin / Inlet",          "حوض تجميع / مدخل",             2),
    ("WET_SW",   "SW_MH",       "Storm Manhole",                "بيار تصريف أمطار",             3),
    ("WET_FOUL", "FOUL_PIPE",   "Foul Sewer Pipe",              "أنبوب صرف صحي",                1),
    ("WET_FOUL", "FOUL_MH",     "Foul Manhole",                 "بيار صرف صحي",                 2),

    # --- Dry Utilities ---
    ("DRY_LV",   "LV_DUCT",     "LV Electrical Duct",           "قناة كهرباء منخفضة",           1),
    ("DRY_LV",   "LV_CABLE",    "LV Cable",                     "كابل كهرباء منخفضة",           2),
    ("DRY_LIGHT","LT_POLE",     "Street Light Pole",            "عمود إنارة",                   1),
    ("DRY_LIGHT","LT_CABLE",    "Lighting Cable",               "كابل إنارة",                   2),
    ("DRY_TEL",  "TEL_2W",      "Telecom 2-Way Conduit",        "قناة اتصالات ثنائية",          1),
    ("DRY_TEL",  "TEL_4W",      "Telecom 4-Way Conduit",        "قناة اتصالات رباعية",          2),
    ("DRY_TEL",  "TEL_SLEEVE",  "Telecom UPVC Sleeve",          "غلاف UPVC اتصالات",            3),
    ("DRY_TEL",  "TEL_MH_JRC12","JRC-12 Manhole",               "بيار JRC-12",                  4),
    ("DRY_TEL",  "TEL_PULL",    "Telecom Pull Box",             "صندوق سحب اتصالات",            5),
    ("DRY_TEL",  "TEL_FC",      "Telecom Frame & Cover",        "إطار وغطاء اتصالات",           6),
    ("DRY_ADMCC","ADMCC_COND",  "ADMCC Conduit",                "قناة ADMCC",                   1),
    ("DRY_ADMCC","ADMCC_TURR",  "Service Turret Base",          "قاعدة برج خدمي",               2),
    ("DRY_FOC",  "FOC_PIPE",    "FOC UPVC Pipe",                "أنبوب UPVC للكابل الضوئي",     1),
    ("DRY_FOC",  "FOC_TRENCH",  "FOC Trench",                   "خندق الكابل الضوئي",           2),
    ("DRY_MCC",  "MCC_PULL",    "MCC Pull Box",                 "صندوق سحب MCC",                1),
    ("DRY_MCC",  "MCC_DUCT",    "MCC Duct",                     "قناة MCC",                     2),

    # --- Civil Structures ---
    ("ST_MH",    "MH_JRC12",    "JRC-12 Manhole Structure",     "بيار JRC-12 (هيكل)",           1),
    ("ST_MH",    "MH_PULLBOX",  "Pull Box Chamber",             "غرفة صندوق سحب",               2),
    ("ST_MH",    "MH_FP",       "Feeder Pillar Base",           "قاعدة عمود تغذية",             3),
    ("ST_MH",    "MH_SEWER",    "Sewer Manhole",                "بيار صرف",                     4),
    ("ST_CROSS", "CR_CONC",     "Concrete Road Crossing",       "تقاطع طريق خرساني",            1),
    ("ST_CROSS", "CR_UPVC",     "UPVC Sleeve Crossing",         "تقاطع غلاف UPVC",              2),
    ("ST_PUMP",  "PS_ROOM",     "Pump Station Room",            "غرفة محطة الضخ",               1),
    ("ST_ELEC",  "ER_ROOM",     "Electrical Room",              "غرفة كهرباء",                  1),
    ("ST_FOUND", "FD_EXC",      "Foundation Excavation",        "حفر أساسات",                   1),
    ("ST_FOUND", "FD_BLIND",    "Foundation Blinding",          "خرسانة نظافة الأساس",          2),

    # --- Landscape ---
    ("LS_SOFT",  "LS_TURF",     "Turf / Grass",                 "عشب",                          1),
    ("LS_SOFT",  "LS_TREE",     "Trees & Shrubs",               "أشجار وشجيرات",                2),
    ("LS_HARD",  "LS_PAVE",     "Hardscape Paving",             "رصف تنسيق صلب",                1),
    ("LS_PUMP",  "LS_PUMP_EQ",  "Irrigation Pump Equipment",    "معدات مضخات الري",             1),
]

# ==============================================================================
#  L4: WORK TYPES
# ==============================================================================
WORK_TYPES = [
    ("EXC",     "Excavation",                 "حفر",                1),
    ("FORM",    "Formation & Blinding",       "تشكيل وخرسانة نظافة",2),
    ("LAY",     "Laying / Installation",      "تمديد / تركيب",      3),
    ("JOINT",   "Jointing",                   "وصل",                4),
    ("BACK",    "Backfill",                   "ردم",                5),
    ("COMP",    "Compaction",                 "دمك",                6),
    ("TEST",    "Testing",                    "اختبار",             7),
    ("SURV",    "Surveying / Audit",          "مسح / تدقيق",        8),
    ("FC_INST", "Frame & Cover Installation", "تركيب إطار وغطاء",   9),
    ("ENCASE",  "Concrete Encasement",        "تغليف خرساني",       10),
    ("CONSTR",  "Construction",               "إنشاء",              11),
    ("INST",    "Installation",               "تركيب",              12),
]

# ==============================================================================
#  L5: STAGES
# ==============================================================================
STAGES = [
    ("L1",     "Layer 1",        "الطبقة 1",     1),
    ("L2",     "Layer 2",        "الطبقة 2",     2),
    ("L3",     "Layer 3",        "الطبقة 3",     3),
    ("BASE",   "Base Course",    "طبقة الأساس",  4),
    ("FINAL",  "Final",          "نهائي",        5),
    ("ASBUILT","As-Built",       "حسب التنفيذ",  6),
    ("VERIFY", "Verification",   "تحقق",         7),
    ("NA",     "N/A",            "غير محدد",     99),
]

# ==============================================================================
#  ROADS (extracted from actual data)
# ==============================================================================
ROADS = [
    # (code, name_en, name_ar, road_type, sort_order)
    ("RD-01", "Road 01",       "طريق 01",        "road",       1),
    ("RD-02", "Road 02",       "طريق 02",        "road",       2),
    ("RD-04", "Road 04",       "طريق 04",        "road",       4),
    ("RD-05", "Road 05",       "طريق 05",        "road",       5),
    ("RD-06", "Road 06",       "طريق 06",        "road",       6),
    ("RD-07", "Road 07",       "طريق 07",        "road",       7),
    ("RD-08", "Road 08",       "طريق 08",        "road",       8),
    ("RD-09", "Road 09",       "طريق 09",        "road",       9),
    ("RA-01", "Roundabout 01", "دوار 01",        "roundabout", 10),
    ("RA-02", "Roundabout 02", "دوار 02",        "roundabout", 11),
    ("COMMON","Common Areas",  "مناطق مشتركة",   "common",     90),
    ("IPS",   "IPS Building",  "مبنى IPS",       "building",   91),
]

# ==============================================================================
#  ASSET SEGMENTS
# ==============================================================================
ASSET_SEGMENTS = [
    ("LHS",        "LHS (Left Side)",          "الجانب الأيسر",       1),
    ("RHS",        "RHS (Right Side)",         "الجانب الأيمن",       2),
    ("CARR",       "Carriageway",              "ساحة الطريق",         3),
    ("SW",         "Sidewalk",                 "رصيف المشاة",         4),
    ("SERV",       "Service Road",             "طريق خدمي",           5),
    ("WALK",       "Walkway",                  "ممر مشاة",            6),
    ("BOTH",       "Both Sides (LHS & RHS)",   "كلا الجانبين",        7),
    ("FULL",       "Full Width",               "كامل العرض",          8),
    ("NA",         "N/A",                      "غير محدد",            99),
]


# ==============================================================================
#  SEED FUNCTION
# ==============================================================================
def seed_all():
    """Populates all reference tables. Idempotent — uses INSERT OR REPLACE."""
    init_db()
    conn = get_conn()
    c = conn.cursor()

    # Disciplines
    for i, (code, en, ar, sort) in enumerate(DISCIPLINES, start=1):
        c.execute("INSERT OR REPLACE INTO ref_discipline (id, code, name_en, name_ar, sort_order) VALUES (?,?,?,?,?)",
                  (i, code, en, ar, sort))
    disc_map = {row[1]: row[0] for row in c.execute("SELECT id, code FROM ref_discipline").fetchall()}

    # Systems
    sys_map = {}
    sid_counter = 1
    for d_code, s_code, en, ar, sort in SYSTEMS:
        did = disc_map[d_code]
        c.execute("INSERT OR REPLACE INTO ref_system (id, discipline_id, code, name_en, name_ar, sort_order) VALUES (?,?,?,?,?,?)",
                  (sid_counter, did, s_code, en, ar, sort))
        sys_map[s_code] = sid_counter
        sid_counter += 1

    # Components
    comp_map = {}
    cid_counter = 1
    for s_code, c_code, en, ar, sort in COMPONENTS:
        sid = sys_map[s_code]
        c.execute("INSERT OR REPLACE INTO ref_component (id, system_id, code, name_en, name_ar, sort_order) VALUES (?,?,?,?,?,?)",
                  (cid_counter, sid, c_code, en, ar, sort))
        comp_map[c_code] = cid_counter
        cid_counter += 1

    # Work types
    wt_map = {}
    wt_counter = 1
    for code, en, ar, sort in WORK_TYPES:
        c.execute("INSERT OR REPLACE INTO ref_work_type (id, code, name_en, name_ar, sort_order) VALUES (?,?,?,?,?)",
                  (wt_counter, code, en, ar, sort))
        wt_map[code] = wt_counter
        wt_counter += 1

    # Stages
    st_map = {}
    st_counter = 1
    for code, en, ar, sort in STAGES:
        c.execute("INSERT OR REPLACE INTO ref_stage (id, code, name_en, name_ar, sort_order) VALUES (?,?,?,?,?)",
                  (st_counter, code, en, ar, sort))
        st_map[code] = st_counter
        st_counter += 1

    # Roads
    road_map = {}
    rd_counter = 1
    for code, en, ar, rtype, sort in ROADS:
        c.execute("INSERT OR REPLACE INTO ref_road (id, code, name_en, name_ar, road_type, sort_order) VALUES (?,?,?,?,?,?)",
                  (rd_counter, code, en, ar, rtype, sort))
        road_map[code] = rd_counter
        rd_counter += 1

    # Asset segments
    seg_map = {}
    seg_counter = 1
    for code, en, ar, sort in ASSET_SEGMENTS:
        c.execute("INSERT OR REPLACE INTO ref_asset_segment (id, code, name_en, name_ar, sort_order) VALUES (?,?,?,?,?)",
                  (seg_counter, code, en, ar, sort))
        seg_map[code] = seg_counter
        seg_counter += 1

    conn.commit()
    conn.close()

    return {
        "disciplines": len(DISCIPLINES),
        "systems": len(SYSTEMS),
        "components": len(COMPONENTS),
        "work_types": len(WORK_TYPES),
        "stages": len(STAGES),
        "roads": len(ROADS),
        "segments": len(ASSET_SEGMENTS),
    }


if __name__ == "__main__":
    stats = seed_all()
    print(f"[OK] Reference data seeded:")
    for k, v in stats.items():
        print(f"   - {k}: {v}")
