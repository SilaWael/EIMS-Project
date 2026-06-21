# -*- coding: utf-8 -*-
"""
EIMS Charts Module
==================
Interactive Plotly charts for the dashboard.

All charts are bilingual (EN/AR) and respect the user's language setting.
Charts:
  1. Cumulative time-series by discipline
  2. Distribution donut by discipline
  3. Roads heatmap (records per road per discipline)
  4. Monthly stacked bar
  5. KPI cards (weekly growth, daily average, etc.)
"""
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from datetime import datetime, timedelta

from core.logger import get_logger

log = get_logger(__name__)


# ==============================================================================
#  THEME COLORS
# ==============================================================================
DISCIPLINE_COLORS = {
    "Earthworks & Formation": "#0284c7",     # Blue
    "Roadworks & Paving": "#10b981",          # Green
    "Wet Utilities (Hydraulic)": "#06b6d4",  # Cyan
    "Dry Utilities (Electrical/Comm)": "#f59e0b",  # Amber
    "Civil Structures": "#8b5cf6",            # Purple
    "Landscape & Soft Works": "#84cc16",     # Lime
}

# Arabic versions of the same disciplines
DISCIPLINE_COLORS_AR = {
    "أعمال الحفر والتشكيل": "#0284c7",
    "أعمال الطرق والرصف": "#10b981",
    "الشبكات الرطبة (الهيدروليكية)": "#06b6d4",
    "الشبكات الجافة (كهرباء/اتصالات)": "#f59e0b",
    "المنشآت المدنية": "#8b5cf6",
    "أعمال التنسيق والزراعة": "#84cc16",
}


def _get_color(discipline_label, lang='en'):
    """Returns a consistent color for a discipline label."""
    colors = DISCIPLINE_COLORS_AR if lang == 'ar' else DISCIPLINE_COLORS
    return colors.get(discipline_label, "#64748b")  # slate as fallback


def _get_layout(lang='en'):
    """Common layout config for all charts."""
    return dict(
        font=dict(family="Cairo, Outfit, sans-serif", size=12),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=20, r=20, t=50, b=20),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right" if lang == 'ar' else "left",
            x=1 if lang == 'ar' else 0,
        ),
    )


# ==============================================================================
#  CHART 1: CUMULATIVE TIME-SERIES BY DISCIPLINE
# ==============================================================================
def chart_cumulative_timeseries(df, lang='en'):
    """Line chart showing cumulative quantity over time, per discipline."""
    if df.empty:
        return None

    disc_col = 'discipline_en' if lang == 'en' else 'discipline_ar'
    if disc_col not in df.columns:
        return None

    # Parse dates (already in DD-MM-YYYY display format)
    df = df.copy()
    df['date_parsed'] = pd.to_datetime(df['report_date'], format='%d-%m-%Y', errors='coerce')
    df = df.dropna(subset=['date_parsed'])

    if df.empty:
        return None

    # Group by date + discipline, sum quantities
    daily = df.groupby(['date_parsed', disc_col])['quantity'].sum().reset_index()
    # Cumulative sum per discipline
    daily = daily.sort_values([disc_col, 'date_parsed'])
    daily['cumulative'] = daily.groupby(disc_col)['quantity'].cumsum()

    fig = go.Figure()
    for disc in daily[disc_col].unique():
        disc_data = daily[daily[disc_col] == disc]
        fig.add_trace(go.Scatter(
            x=disc_data['date_parsed'],
            y=disc_data['cumulative'],
            mode='lines+markers',
            name=str(disc),
            line=dict(color=_get_color(disc, lang), width=3),
            marker=dict(size=6),
            hovertemplate=f"<b>{disc}</b><br>Date: %{{x|%Y-%m-%d}}<br>Cumulative: %{{y:,.1f}} m<extra></extra>",
            fill='tozeroy',
            fillcolor=_get_color(disc, lang).replace(')', ', 0.1)').replace('rgb', 'rgba') if 'rgb' in _get_color(disc, lang) else None,
        ))

    title = "التراكم الزمني للكميات حسب التخصص" if lang == 'ar' else "Cumulative Quantities by Discipline Over Time"
    fig.update_layout(
        title=dict(text=title, x=0.5, font=dict(size=16)),
        xaxis_title="التاريخ" if lang == 'ar' else "Date",
        yaxis_title="الكمية التراكمية (م)" if lang == 'ar' else "Cumulative Quantity (m)",
        hovermode="x unified",
        **_get_layout(lang),
    )
    fig.update_xaxes(tickformat="%d-%m-%Y", gridcolor='rgba(0,0,0,0.05)')
    fig.update_yaxes(gridcolor='rgba(0,0,0,0.05)')
    return fig


# ==============================================================================
#  CHART 2: DISTRIBUTION DONUT BY DISCIPLINE
# ==============================================================================
def chart_distribution_donut(df, lang='en'):
    """Donut chart showing percentage distribution by discipline."""
    if df.empty:
        return None

    disc_col = 'discipline_en' if lang == 'en' else 'discipline_ar'
    if disc_col not in df.columns:
        return None

    grouped = df.groupby(disc_col)['quantity'].sum().reset_index()
    grouped = grouped.sort_values('quantity', ascending=False)

    colors = [_get_color(d, lang) for d in grouped[disc_col]]

    title = "توزيع الكميات حسب التخصص" if lang == 'ar' else "Quantity Distribution by Discipline"
    fig = go.Figure(data=[go.Pie(
        labels=grouped[disc_col],
        values=grouped['quantity'],
        hole=0.55,
        marker=dict(colors=colors, line=dict(color="white", width=2)),
        textinfo='label+percent',
        textposition='outside',
        hovertemplate="<b>%{label}</b><br>Quantity: %{value:,.1f} m<br>Percentage: %{percent}<extra></extra>",
    )])
    fig.update_layout(
        title=dict(text=title, x=0.5, font=dict(size=16)),
        showlegend=False,
        **_get_layout(lang),
    )
    return fig


# ==============================================================================
#  CHART 3: ROADS HEATMAP
# ==============================================================================
def chart_roads_heatmap(df, lang='en'):
    """Heatmap of records per road per discipline."""
    if df.empty:
        return None

    disc_col = 'discipline_en' if lang == 'en' else 'discipline_ar'
    if disc_col not in df.columns or 'road_code' not in df.columns:
        return None

    # Filter out NaN roads
    df_roads = df.dropna(subset=['road_code']).copy()
    if df_roads.empty:
        return None

    pivot = df_roads.pivot_table(
        index='road_code',
        columns=disc_col,
        values='id',
        aggfunc='count',
        fill_value=0
    )

    title = "توزيع السجلات: الطرق × التخصصات" if lang == 'ar' else "Records Distribution: Roads × Disciplines"
    fig = go.Figure(data=go.Heatmap(
        z=pivot.values,
        x=pivot.columns.tolist(),
        y=pivot.index.tolist(),
        colorscale='Blues',
        hovertemplate="<b>Road: %{y}</b><br>Discipline: %{x}<br>Records: %{z}<extra></extra>",
        text=pivot.values,
        texttemplate="%{text}",
        textfont={"size": 11},
    ))
    fig.update_layout(
        title=dict(text=title, x=0.5, font=dict(size=16)),
        xaxis_title="التخصص" if lang == 'ar' else "Discipline",
        yaxis_title="الطريق" if lang == 'ar' else "Road",
        **_get_layout(lang),
    )
    return fig


# ==============================================================================
#  CHART 4: MONTHLY STACKED BAR
# ==============================================================================
def chart_monthly_stacked(df, lang='en'):
    """Stacked bar chart of monthly quantities by discipline."""
    if df.empty:
        return None

    disc_col = 'discipline_en' if lang == 'en' else 'discipline_ar'
    if disc_col not in df.columns:
        return None

    df = df.copy()
    df['date_parsed'] = pd.to_datetime(df['report_date'], format='%d-%m-%Y', errors='coerce')
    df = df.dropna(subset=['date_parsed'])
    if df.empty:
        return None

    df['month'] = df['date_parsed'].dt.strftime('%Y-%m')
    monthly = df.groupby(['month', disc_col])['quantity'].sum().reset_index()

    title = "الكميات الشهرية المكدّدة" if lang == 'ar' else "Monthly Stacked Quantities"
    fig = go.Figure()
    for disc in monthly[disc_col].unique():
        disc_data = monthly[monthly[disc_col] == disc]
        fig.add_trace(go.Bar(
            x=disc_data['month'],
            y=disc_data['quantity'],
            name=str(disc),
            marker_color=_get_color(disc, lang),
            hovertemplate=f"<b>{disc}</b><br>Month: %{{x}}<br>Quantity: %{{y:,.1f}} m<extra></extra>",
        ))

    fig.update_layout(
        title=dict(text=title, x=0.5, font=dict(size=16)),
        xaxis_title="الشهر" if lang == 'ar' else "Month",
        yaxis_title="الكمية (م)" if lang == 'ar' else "Quantity (m)",
        barmode='stack',
        **_get_layout(lang),
    )
    return fig


# ==============================================================================
#  CHART 5: WEEKLY ACTIVITY (BAR)
# ==============================================================================
def chart_weekly_activity(df, lang='en'):
    """Bar chart of records created per week (last 8 weeks)."""
    if df.empty:
        return None

    df = df.copy()
    df['date_parsed'] = pd.to_datetime(df['report_date'], format='%d-%m-%Y', errors='coerce')
    df = df.dropna(subset=['date_parsed'])
    if df.empty:
        return None

    df['week'] = df['date_parsed'].dt.strftime('%Y-W%U')
    weekly = df.groupby('week').size().reset_index(name='records')
    weekly = weekly.sort_values('week').tail(8)

    title = "النشاط الأسبوعي (آخر 8 أسابيع)" if lang == 'ar' else "Weekly Activity (Last 8 Weeks)"
    fig = go.Figure(data=[go.Bar(
        x=weekly['week'],
        y=weekly['records'],
        marker_color='#0284c7',
        hovertemplate="<b>%{x}</b><br>Records: %{y}<extra></extra>",
        text=weekly['records'],
        textposition='outside',
    )])
    fig.update_layout(
        title=dict(text=title, x=0.5, font=dict(size=16)),
        xaxis_title="الأسبوع" if lang == 'ar' else "Week",
        yaxis_title="عدد السجلات" if lang == 'ar' else "Number of Records",
        **_get_layout(lang),
    )
    return fig


# ==============================================================================
#  KPI CALCULATIONS
# ==============================================================================
def compute_kpis(df, lang='en'):
    """Returns a dict of KPI values for display."""
    if df.empty:
        return {}

    df = df.copy()
    df['date_parsed'] = pd.to_datetime(df['report_date'], format='%d-%m-%Y', errors='coerce')
    df = df.dropna(subset=['date_parsed'])

    kpis = {
        'total_records': len(df),
        'total_qty': float(df['quantity'].sum()),
        'unique_roads': int(df['road_code'].dropna().nunique()),
        'date_range_days': int((df['date_parsed'].max() - df['date_parsed'].min()).days) + 1 if len(df) > 1 else 1,
        'daily_avg_records': 0.0,
        'daily_avg_qty': 0.0,
        'last_7d_records': 0,
        'last_7d_qty': 0.0,
        'prev_7d_records': 0,
        'growth_pct': 0.0,
    }

    if kpis['date_range_days'] > 0:
        kpis['daily_avg_records'] = round(kpis['total_records'] / kpis['date_range_days'], 1)
        kpis['daily_avg_qty'] = round(kpis['total_qty'] / kpis['date_range_days'], 1)

    # Last 7 days vs previous 7 days
    today = df['date_parsed'].max()
    last_7d_start = today - timedelta(days=7)
    prev_7d_start = today - timedelta(days=14)

    last_7d = df[(df['date_parsed'] > last_7d_start) & (df['date_parsed'] <= today)]
    prev_7d = df[(df['date_parsed'] > prev_7d_start) & (df['date_parsed'] <= last_7d_start)]

    kpis['last_7d_records'] = len(last_7d)
    kpis['last_7d_qty'] = float(last_7d['quantity'].sum())
    kpis['prev_7d_records'] = len(prev_7d)

    if kpis['prev_7d_records'] > 0:
        kpis['growth_pct'] = round(
            ((kpis['last_7d_records'] - kpis['prev_7d_records']) / kpis['prev_7d_records']) * 100, 1
        )

    return kpis
