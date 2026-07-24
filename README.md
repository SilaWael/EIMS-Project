# EIMS — Engineering Information Management System (Cloud Edition)

Cloud-native version of the EIMS Streamlit app for the ADHA Infrastructure Project (108 Villas).

## Architecture

| Layer | Technology | Purpose |
|---|---|---|
| **Frontend** | Streamlit Cloud | Interactive dashboard |
| **Database** | Supabase Postgres | `master_registry` table |
| **Storage** | Supabase Storage | 3 buckets: `finished-pdfs`, `processed-audits`, `csv-database` |
| **Source control** | GitHub | Auto-redeploy to Streamlit Cloud |

## Files

```
.
├── app.py                          # Main Streamlit app
├── db.py                           # Supabase adapter (replaces SQLite)
├── requirements.txt                # Python dependencies
├── .streamlit/
│   ├── config.toml                 # Streamlit config
│   └── example_secrets.toml        # Template for Streamlit Cloud secrets
└── README.md
```

## Deployment on Streamlit Cloud

1. **Fork / clone this repo** to your GitHub.

2. **Go to Streamlit Cloud**: https://share.streamlit.io/

3. **Create new app**:
   - Repository: `<your-username>/EIMS-Project`
   - Branch: `main`
   - Main file path: `app.py`
   - Requirements file: `requirements.txt`

4. **Add Secrets** (App Settings → Secrets → TOML format):

```toml
[database]
SUPABASE_URL = "https://udpurwnjsoevszohnunr.supabase.co"
SUPABASE_ANON_KEY = "..."
SUPABASE_SERVICE_ROLE_KEY = "..."
DB_PASSWORD = "..."
PROJECT_REF = "udpurwnjsoevszohnunr"
POOLER_HOST = "aws-0-ap-southeast-1.pooler.supabase.com"

[storage]
BUCKET_PDFS = "finished-pdfs"
BUCKET_AUDITS = "processed-audits"
BUCKET_CSVS = "csv-database"

[app]
ADMIN_PASSWORD = "1212"
```

5. **Save & Deploy**. The app will be live at `https://<your-app>.streamlit.app`.

## Local Development

```bash
pip install -r requirements.txt
cp .streamlit/example_secrets.toml .env  # then edit values
streamlit run app.py
```

## Supervisor

Eng. Wael Radwan — ADHA Project (108 Villas)
