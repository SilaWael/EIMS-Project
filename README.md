# EIMS - Engineering Information Management System

نظام إدارة المعلومات الهندسية - EIMS
=====================================

Smart Engineering Information Management System for infrastructure projects.

## Features

- **Hierarchical Classification**: 5 levels (Discipline → System → Component → Work Type → Stage)
- **Bilingual UI**: English + Arabic with full RTL support
- **Interactive Dashboard**: KPIs, charts (Plotly), and detailed records
- **PDF Archive**: Store PDF/HTML as BLOBs in DB (cloud-friendly) or filesystem
- **Excel Export**: 4-sheet styled reports (Master + Discipline Summary + Road Summary + Monthly Trends)
- **PDF Reports**: Professional reports with cover page, KPIs, and signature block
- **Secure Auth**: bcrypt + pepper + auto-recovery
- **Auto-Backup**: Before every delete/reset operation
- **96 pytest tests** ensuring quality

## Quick Start

### Local Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/YOUR_USERNAME/EIMS.git
   cd EIMS
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the app**:
   ```bash
   streamlit run app.py
   ```

4. **Default password**: `1212` (change it on first login via the Importer page)

### Deploy to Streamlit Cloud

1. Push this repository to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Click "New app"
4. Select your GitHub repository
5. Set the main file path to `app.py`
6. Click "Deploy"

**Note**: Streamlit Cloud's filesystem is ephemeral. To persist data:
- The SQLite database (`eims.db`) is committed to the repo, so changes pushed to GitHub will appear in the cloud app
- PDFs/HTML files should be migrated to BLOB storage via the "PDF Archive" page before deploying
- For real-time updates, use the local app for data entry, then commit + push to sync

### Usage Workflow

1. **Add records**: Importer page (password required) → Upload CSV
2. **View analytics**: Dashboard page → Charts, KPIs, filters
3. **Manage PDFs**: PDF Archive page → Upload/migrate/view documents
4. **Export reports**: Dashboard → Analytics section → Excel/CSV/PDF buttons

## Project Structure

```
EIMS/
├── app.py                    # Main Streamlit app
├── database.py               # SQLite layer with BLOB storage
├── classification_seed.py    # Hierarchical classification data
├── migrate_v1_to_v2.py       # V1 → V2 migration script
├── i18n.py                   # Translations (EN/AR)
├── reset_password.py         # Password reset utility
│
├── core/                     # Core modules
│   ├── logger.py             # Logging system
│   ├── backup.py             # Database backups
│   ├── exporter.py           # Excel/CSV export
│   ├── pdf_report.py         # PDF report generation
│   ├── os_compat.py          # Cross-platform helpers
│   └── st_compat.py          # Streamlit version compatibility
│
├── auth/                     # Authentication
│   └── auth.py               # bcrypt + pepper
│
├── ui/                       # UI components
│   ├── admin.py              # Admin panel
│   ├── charts.py             # 5 Plotly charts
│   ├── pagination.py         # Table pagination
│   └── pdf_archive.py        # PDF management
│
├── tests/                    # 96 pytest tests
├── .streamlit/config.toml    # Streamlit theme
├── .github/workflows/        # CI tests
└── requirements.txt
```

## Testing

```bash
python -m pytest tests/ -v
```

## License

Private project — 108 Villas Project (ADHA).

## Supervision

Eng. Wael Radwan
