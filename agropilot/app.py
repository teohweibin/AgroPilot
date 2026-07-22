"""
app.py — AgriQuote · Dark UI matching QuotePilot V3.0 design
Run: streamlit run app.py
"""

import os, time, queue, threading
import streamlit as st
import pandas as pd
import pathlib
from agent_configuration.agent import build_graph, QuoteState, _calculate_totals
from dotenv import load_dotenv


# ─────────────────────────────────────────────────────────────────────────────
# GMAIL INBOX LOADER (optional RFQ source)
# ─────────────────────────────────────────────────────────────────────────────

def _gmail_extract_text(payload: dict) -> str:
    """Extract best-effort plain text from Gmail API message payload."""
    import base64

    def _decode(data: str) -> str:
        if not data:
            return ""
        try:
            return base64.urlsafe_b64decode(data.encode("utf-8")).decode("utf-8", errors="replace")
        except Exception:
            return ""

    # Direct body
    body = (payload.get("body") or {}).get("data")
    if body:
        return _decode(body)

    # Multipart walk
    parts = payload.get("parts") or []
    stack = list(parts)
    best_plain = ""
    best_html = ""
    while stack:
        p = stack.pop(0) or {}
        mime = (p.get("mimeType") or "").lower()
        bdata = ((p.get("body") or {}).get("data")) or ""
        if mime == "text/plain" and bdata:
            best_plain = best_plain or _decode(bdata)
        elif mime == "text/html" and bdata:
            best_html = best_html or _decode(bdata)
        stack.extend(p.get("parts") or [])

    if best_plain.strip():
        return best_plain
    if best_html.strip():
        # Simple HTML strip fallback
        import re
        text = re.sub(r"<[^>]+>", " ", best_html)
        text = re.sub(r"\s+", " ", text).strip()
        return text
    return ""


def gmail_fetch_latest_rfq(query: str, token_path: str) -> dict:
    """Fetch latest Gmail message matching `query` and return {subject, from, date, body}."""
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    scopes = [
        "https://www.googleapis.com/auth/gmail.readonly"
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/gmail.compose",
        ]
    if not os.path.exists(token_path):
        return {"success": False, "error": f"Gmail token file not found at {token_path}"}

    creds = Credentials.from_authorized_user_file(token_path, scopes)
    service = build("gmail", "v1", credentials=creds)

    resp = service.users().messages().list(userId="me", q=query, maxResults=1).execute()
    msgs = resp.get("messages") or []
    if not msgs:
        return {"success": False, "error": f"No Gmail messages matched query: {query}"}

    msg_id = msgs[0]["id"]
    msg = service.users().messages().get(userId="me", id=msg_id, format="full").execute()
    headers = {h.get("name", "").lower(): h.get("value", "") for h in (msg.get("payload", {}).get("headers") or [])}
    payload = msg.get("payload") or {}

    body_text = _gmail_extract_text(payload)
    return {
        "success": True,
        "id": msg_id,
        "subject": headers.get("subject", ""),
        "from": headers.get("from", ""),
        "date": headers.get("date", ""),
        "body": body_text,
    }


DEMO_RFQ = """FROM: Sarah Lim <sarah.lim@greenfields-demo.example>
SUBJECT: RFQ — 330 HP precision tractor package for Johor farm

Hello AgroPilot team,

GreenFields Farm is expanding its maize operation in Johor, Malaysia. Please prepare a quote for a 330 HP tractor with high-flow hydraulics, an operator comfort cab, GPS guidance, and a precision planter integration kit.

We operate 1,200 acres and need delivery before the next planting window. Please include an itemised configuration, a compatibility review, and the total estimated cost.

Regards,
Sarah Lim
Farm Operations Manager
"""

# ─────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="AgriQuote — Autonomous Sales Engineer",
    page_icon="🌾",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─────────────────────────────────────────────────────────────────────────────
# GLOBAL PREMIUM V3.0 DARK CSS INJECTION (LARGER WORD SIZES & GLOW DESIGNS)
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;700;800&display=swap');

  .stApp, [data-testid="stAppViewContainer"] {
    background: #060913 !important;
    color: #e2e8f0 !important;
    font-family: 'Inter', -apple-system, sans-serif !important;
  }
  [data-testid="stSidebar"] { background: #090e1a !important; }
  [data-testid="stHeader"] { background: rgba(0,0,0,0) !important; }

  #MainMenu, footer, header { visibility: hidden; }

  h1, h2, h3, h4, h5, h6 {
    font-family: 'Inter', -apple-system, sans-serif !important;
    font-weight: 800 !important;
    letter-spacing: -0.025em !important;
  }

  .monospace-text, code, pre, .bom-table, .timer-value, .log-entry, .hitl-metric-value, .sum-val {
    font-family: 'JetBrains Mono', monospace !important;
  }

  .nav-bar {
    display: flex; align-items: center; justify-content: space-between;
    padding: 20px 36px; background: #090f1e;
    border-bottom: 1px solid #1e293b; margin-bottom: 28px;
    border-radius: 8px;
  }
  .nav-logo { display: flex; align-items: center; gap: 14px; }
  .nav-logo-box {
    background: linear-gradient(135deg, #7b6ef6, #5865f2);
    color: #ffffff; font-weight: 900;
    font-size: 15px; padding: 8px 14px; border-radius: 6px;
    letter-spacing: 0.05em;
    box-shadow: 0 0 20px rgba(90, 101, 242, 0.4);
  }
  .nav-title { color: #ffffff; font-size: 19px; font-weight: 800; letter-spacing: 0.04em; }
  .nav-version { color: #7b6ef6; font-size: 14px; margin-left: 6px; font-weight: 700; }
  .nav-env {
    background: #0f172a; border: 1px solid #312e81; border-radius: 20px;
    padding: 8px 18px; font-size: 12px; color: #a5b4fc;
    display: flex; align-items: center; gap: 10px; font-weight: 700;
  }
  .env-dot { width: 10px; height: 10px; background: #818cf8;
    border-radius: 50%; display: inline-block; animation: pulse 2s infinite; }
  @keyframes pulse { 0%,100%{opacity:1; transform: scale(1);} 50%{opacity:.4; transform: scale(0.85);} }

  .hero-grid { display: grid; grid-template-columns: 1fr 380px; gap: 24px; padding: 0 0 28px; }
  .hero-left {
    background: linear-gradient(135deg, #091124 0%, #070d19 100%);
    border: 1px solid #1e293b; border-radius: 12px;
    padding: 44px 52px; position: relative; overflow: hidden;
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.05);
  }
  .hero-label { font-size: 12px; color: #7b6ef6; letter-spacing: .15em; font-weight: 800; text-transform: uppercase; margin-bottom: 16px; }
  .hero-headline { font-size: 46px; font-weight: 900; color: #ffffff; line-height: 1.15; margin: 0 0 16px; letter-spacing: -0.03em; }
  .hero-headline span {
    background: linear-gradient(135deg, #a855f7 0%, #7b6ef6 50%, #5865f2 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    text-shadow: 0 0 25px rgba(123, 110, 246, 0.35);
  }
  .hero-sub { font-size: 15px; color: #94a3b8; line-height: 1.7; max-width: 600px; margin-bottom: 0px; }
  .hero-watermark {
    position: absolute; right: 40px; top: 50%; transform: translateY(-50%);
    width: 170px; height: 170px; border: 2px solid #1e293b; border-radius: 4px;
    display: flex; align-items: center; justify-content: center;
    font-size: 90px; opacity: .06; font-weight: 300;
  }
  .hero-right {
    background: #091124; border: 1px solid #1e293b; border-radius: 12px;
    padding: 36px; display: flex; flex-direction: column; align-items: center; justify-content: center;
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.05);
  }
  .timer-label { font-size: 12px; color: #64748b; letter-spacing: .12em; font-weight: 800; text-transform: uppercase; margin-bottom: 14px; }
  .timer-value { font-size: 68px; font-weight: 800; color: #00ff87; letter-spacing: .02em; line-height: 1; text-shadow: 0 0 25px rgba(0,255,135,0.35); }
  .timer-compare { font-size: 13.5px; color: #94a3b8; margin-top: 14px; font-weight: 600; }
  .timer-compare span { color: #f43f5e; font-weight: 800; }

  .pipeline-bar {
    display: flex; align-items: center;
    padding: 16px 20px 36px; gap: 0;
  }
  .pipe-step { display: flex; flex-direction: column; align-items: center; flex: 1; }
  .pipe-circle {
    width: 40px; height: 40px; border-radius: 50%;
    border: 2px solid #1e293b; background: #060913;
    display: flex; align-items: center; justify-content: center;
    font-size: 14px; color: #64748b; position: relative; z-index: 2;
    transition: all 0.4s cubic-bezier(0.16, 1, 0.3, 1);
    font-weight: 800;
  }
  .pipe-circle.done { border-color: #10b981; background: #064e3b; color: #34d399; box-shadow: 0 0 15px rgba(16,185,129,0.3); }
  .pipe-circle.active { border-color: #7b6ef6; background: #1e1b4b; color: #a5b4fc;
    box-shadow: 0 0 20px rgba(123,110,246,0.65); transform: scale(1.15); }
  .pipe-circle.pending { border-color: #1e293b; color: #475569; }
  .pipe-label { font-size: 11px; color: #64748b; margin-top: 10px; text-align: center; letter-spacing: .06em; font-weight: 800; text-transform: uppercase; }
  .pipe-label.done { color: #34d399; }
  .pipe-label.active { color: #a5b4fc; }
  .pipe-connector { flex: 1; height: 2px; background: #1e293b; margin-top: -26px; position: relative; z-index: 1; }
  .pipe-connector.done { background: linear-gradient(90deg, #10b981, #7b6ef6); }

  .main-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 28px; padding: 0 0 28px; }

  .panel {
    background: #091124; border: 1px solid #1e293b; border-radius: 12px; overflow: hidden;
    box-shadow: 0 6px 24px rgba(0,0,0,0.22), inset 0 1px 0 rgba(255,255,255,0.02);
    margin-bottom: 24px;
  }
  .panel-header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 16px 24px; border-bottom: 1px solid #1e293b;
    background: #0c152b;
  }
  .panel-title { font-size: 13.5px; font-weight: 900; color: #cbd5e1; letter-spacing: .12em; text-transform: uppercase; }
  .panel-badge {
    font-size: 11px; font-weight: 800; padding: 5px 13px; border-radius: 20px;
    letter-spacing: .06em; text-transform: uppercase; border: 1px solid transparent;
  }
  .badge-parsed   { background: #064e3b; color: #34d399; border-color: #059669; }
  .badge-awaiting { background: #78350f; color: #fbbf24; border-color: #d97706; }
  .badge-final    { background: #1e1b4b; color: #a5b4fc; border-color: #4f46e5; }
  .badge-cleared  { background: #064e3b; color: #34d399; border-color: #059669; }
  .badge-error    { background: #4c0519; color: #fda4af; border-color: #be123c; }
  .panel-body { padding: 22px; }

  .rfq-text {
    font-size: 13.5px; color: #94a3b8; line-height: 1.8;
    max-height: 300px; overflow-y: auto; white-space: pre-wrap;
    padding: 14px; background: #050b16; border-radius: 8px;
    border: 1px solid #111a2e;
  }

  .log-entry { display: flex; gap: 14px; padding: 10px 0; border-bottom: 1px solid #111a2e; font-size: 13px; line-height: 1.5; }
  .log-time { color: #475569; min-width: 50px; font-weight: bold; }
  .log-agent-config { color: #818cf8; font-weight: 800; min-width: 100px; }
  .log-agent-critic { color: #34d399; font-weight: 800; min-width: 100px; }
  .log-agent-sentinel { color: #fbbf24; font-weight: 800; min-width: 100px; }
  .log-agent-system { color: #94a3b8; font-weight: 800; min-width: 100px; }
  .log-msg { color: #e2e8f0; flex: 1; }
  .log-msg.success { color: #34d399; }
  .log-msg.error { color: #f43f5e; }
  .log-msg.warn { color: #fbbf24; }

  .bom-table { width: 100%; border-collapse: collapse; font-size: 13px; }
  .bom-table th { color: #64748b; text-align: left; padding: 10px 12px;
    border-bottom: 1px solid #1e293b; font-weight: 800; letter-spacing: .08em; text-transform: uppercase; }
  .bom-table td { padding: 11px 12px; border-bottom: 1px solid #111a2e; color: #cbd5e1; }
  .bom-table tr:hover td { background: #0c152b; }
  .bom-sku { color: #38bdf8; font-weight: bold; }
  .bom-status-ok { background: #064e3b; color: #34d399; padding: 3px 9px;
    border-radius: 4px; font-size: 11px; font-weight: 800; border: 1px solid #059669; }
  .bom-status-sub { background: #78350f; color: #fbbf24; padding: 3px 9px;
    border-radius: 4px; font-size: 11px; font-weight: 800; border: 1px solid #d97706; }
  .bom-total-row td { font-weight: 800; color: #ffffff; border-top: 1px solid #1e293b;
    border-bottom: none; font-size: 15px; padding-top: 16px; }

  .audit-item {
    border-left: 4.5px solid #f43f5e; background: rgba(244, 63, 94, 0.05);
    padding: 16px 20px; margin-bottom: 14px; border-radius: 0 8px 8px 0;
    border-top: 1px solid rgba(244, 63, 94, 0.12);
    border-right: 1px solid rgba(244, 63, 94, 0.12);
    border-bottom: 1px solid rgba(244, 63, 94, 0.12);
  }
  .audit-item.resolved {
    border-left-color: #10b981; background: rgba(16, 185, 129, 0.05);
    border-top-color: rgba(16,185,129,0.12);
    border-right-color: rgba(16,185,129,0.12);
    border-bottom-color: rgba(16,185,129,0.12);
  }
  .audit-item.warning {
    border-left-color: #fbbf24; background: rgba(251, 191, 36, 0.05);
    border-top-color: rgba(251,191,36,0.12);
    border-right-color: rgba(251,191,36,0.12);
    border-bottom-color: rgba(251,191,36,0.12);
  }
  .audit-sku { font-size: 12px; color: #64748b; margin-bottom: 8px; font-weight: 800; letter-spacing: 0.05em; }
  .audit-issue { font-size: 13.5px; color: #e2e8f0; line-height: 1.6; }
  .audit-action { font-size: 12px; color: #a5b4fc; margin-top: 10px; font-style: italic; font-weight: 600; }
  .audit-resolved-badge { float: right; font-size: 11px; color: #34d399; font-weight: 900; letter-spacing: .06em; }

  .hitl-panel {
    background: #091124; border: 1px solid #1e293b; border-radius: 12px;
    padding: 36px 44px; margin: 0 0 28px;
    box-shadow: 0 12px 36px rgba(0,0,0,0.32), inset 0 1px 0 rgba(255,255,255,0.03);
  }
  .hitl-title { font-size: 13.5px; color: #cbd5e1; letter-spacing: .12em; text-transform: uppercase; margin-bottom: 28px; font-weight: 900; }
  .hitl-metrics { display: grid; grid-template-columns: repeat(5, 1fr); gap: 20px; margin-bottom: 28px; }
  .hitl-metric { text-align: center; background: #050b16; padding: 20px; border-radius: 8px; border: 1px solid #111a2e; }
  .hitl-metric-label { font-size: 11px; color: #64748b; letter-spacing: .08em; text-transform: uppercase; margin-bottom: 10px; font-weight: 800; }
  .hitl-metric-value { font-size: 32px; font-weight: 800; color: #ffffff; }
  .hitl-metric-value.green { color: #00ff87; text-shadow: 0 0 15px rgba(0,255,135,0.25); }
  .hitl-metric-value.yellow { color: #fbbf24; text-shadow: 0 0 15px rgba(251,191,36,0.25); }
  .hitl-rationale { background: #050b16; border-radius: 8px; padding: 20px 24px; font-size: 14px; color: #94a3b8; line-height: 1.7; margin-bottom: 28px; border: 1px solid #111a2e; }

  .completion-screen {
    background: #060913; min-height: 500px;
    display: flex; flex-direction: column; align-items: center;
    justify-content: center; padding: 56px 36px; text-align: center;
  }
  .completion-check {
    width: 88px; height: 88px; border-radius: 50%;
    border: 3px solid #00ff87; display: flex; align-items: center;
    justify-content: center; font-size: 44px; color: #00ff87;
    margin-bottom: 28px;
    box-shadow: 0 0 30px rgba(0,255,135,0.4);
    background: rgba(0, 255, 135, 0.04);
  }
  .completion-title { font-size: 44px; font-weight: 900; color: #ffffff; margin-bottom: 14px; letter-spacing: -0.035em; }
  .completion-sub { font-size: 15px; color: #64748b; margin-bottom: 36px; font-weight: 600; }
  .completion-sub .green { color: #00ff87; font-weight: 800; }
  .completion-sub .red   { color: #f43f5e; font-weight: 800; }
  .completion-actions { display: flex; gap: 16px; margin-bottom: 48px; flex-wrap: wrap; justify-content: center; }
  .action-badge {
    background: #081e17; border: 1px solid #059669; border-radius: 8px;
    padding: 13px 26px; font-size: 13px; color: #34d399; font-weight: 800;
    letter-spacing: .08em; box-shadow: 0 4px 12px rgba(0,0,0,0.35);
  }
  .completion-stats { display: flex; gap: 88px; justify-content: center; border-top: 1px solid #1e293b; padding-top: 40px; width: 100%; max-width: 850px; }
  .stat { text-align: center; }
  .stat-label { font-size: 12px; color: #64748b; text-transform: uppercase; letter-spacing: .12em; margin-bottom: 10px; font-weight: 800; }
  .stat-value { font-size: 28px; font-weight: 800; }
  .stat-value.green { color: #00ff87; text-shadow: 0 0 15px rgba(0,255,135,0.25); }
  .stat-value.yellow { color: #fbbf24; text-shadow: 0 0 15px rgba(251,191,36,0.25); }
  .stat-value.white { color: #ffffff; }

  .stButton > button {
    background: #1e293b !important; color: #f1f5f9 !important;
    border: 1px solid #334155 !important; border-radius: 8px !important;
    font-size: 14px !important; font-weight: 800 !important;
    padding: 14px 32px !important; letter-spacing: .06em !important;
    transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1) !important;
  }
  .stButton > button:hover {
    background: #334155 !important;
    border-color: #475569 !important;
    transform: translateY(-1px);
  }
  .stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #7b6ef6, #5865f2) !important;
    border-color: #818cf8 !important; color: #ffffff !important;
    box-shadow: 0 5px 18px rgba(90, 101, 242, 0.35) !important;
  }
  .stButton > button[kind="primary"]:hover {
    box-shadow: 0 8px 24px rgba(90, 101, 242, 0.5) !important;
  }
  textarea {
    background: #050b16 !important; color: #cbd5e1 !important;
    border: 1px solid #1e293b !important; border-radius: 8px !important;
    font-size: 13.5px !important; line-height: 1.6 !important;
  }
  textarea:focus {
    border-color: #7b6ef6 !important;
    box-shadow: 0 0 0 1px #7b6ef6 !important;
  }

  .stSelectbox div[data-baseweb="select"] {
    background-color: #091124 !important;
    border: 1px solid #1e293b !important;
    border-radius: 8px !important;
  }
  .stSelectbox div[data-baseweb="select"] * {
    color: #cbd5e1 !important;
    font-size: 13.5px !important;
  }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# SESSION STATE
# ─────────────────────────────────────────────────────────────────────────────

if "pipeline_done" not in st.session_state:
    st.session_state.pipeline_done = False
if "final_state"   not in st.session_state:
    st.session_state.final_state   = None
if "elapsed"       not in st.session_state:
    st.session_state.elapsed       = 0
if "all_logs"      not in st.session_state:
    st.session_state.all_logs      = []

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def fmt_time(secs: int) -> str:
    return f"{secs // 60:02d}:{secs % 60:02d}"

AGENT_CLASS = {
    "CONFIGURATOR": "log-agent-config",
    "CRITIC":       "log-agent-critic",
    "SENTINEL":     "log-agent-sentinel",
    "SYSTEM":       "log-agent-system",
}

def render_log(logs: list) -> str:
    if not logs:
        return "<div style='color:#475569;font-size:13px;padding:8px 0'>Waiting for pipeline stream...</div>"
    rows = []
    for i, e in enumerate(logs):
        t  = fmt_time(i * 3)
        ag = e.get("agent", "SYSTEM")
        ag_cls = AGENT_CLASS.get(ag, "log-agent-system")
        lv = e.get("level", "info")
        msg_cls = f"log-msg {lv}" if lv in ("success","error","warn") else "log-msg"
        rows.append(
            f'<div class="log-entry">'
            f'<span class="log-time">{t}</span>'
            f'<span class="{ag_cls}">[{ag}]</span>'
            f'<span class="{msg_cls}">{e.get("msg","")}</span>'
            f'</div>'
        )
    return "".join(rows)


def render_pipeline_bar(active_node: str) -> str:
    steps = [
        ("node_parse",          "RFQ Parse"),
        ("node_configurator",   "Configurator"),
        ("node_critic",         "Critic Review"),
        ("node_configurator2",  "Resolution"),
        ("node_sentinel",       "HITL Approval"),
        ("node_generate_quote", "Sent"),
    ]
    ORDER = [s[0] for s in steps]
    try:
        active_idx = ORDER.index(active_node)
    except ValueError:
        active_idx = -1

    html = '<div class="pipeline-bar">'
    for i, (node, label) in enumerate(steps):
        if i < active_idx:
            state_cls = "done"
            icon = "✓"
        elif i == active_idx:
            state_cls = "active"
            icon = str(i + 1)
        else:
            state_cls = "pending"
            icon = str(i + 1)

        html += f'''
        <div class="pipe-step">
          <div class="pipe-circle {state_cls}">{icon}</div>
          <div class="pipe-label {state_cls}">{label}</div>
        </div>'''

        if i < len(steps) - 1:
            conn_cls = "done" if i < active_idx else ""
            html += f'<div class="pipe-connector {conn_cls}"></div>'

    html += "</div>"
    return html


def render_bom_table(bom: list, totals: dict, currency_symbol: str = "$") -> str:
    if not bom:
        return "<div style='color:#475569;font-size:13px;padding:8px 0'>No components engineered yet.</div>"
    rows = ""
    for item in bom:
        if item.get("status", "") == "REJECTED":
            continue
        st_raw = item.get("status", "DRAFT")
        if "SUBSTITUTED" in st_raw.upper():
            st_html = f'<span class="bom-status-sub">SUB</span>'
        else:
            st_html = f'<span class="bom-status-ok">OK</span>'
        desc = item.get("description", "")[:38]
        rows += f"""<tr>
          <td class="bom-sku">{item.get('sku','')[:22]}</td>
          <td>{desc}</td>
          <td style="text-align:center">{item.get('qty',1)}</td>
          <td style="text-align:right">{currency_symbol}{item.get('unit_price_usd',0):,.0f}</td>
          <td style="text-align:right"><b>{currency_symbol}{item.get('line_total_usd',0):,.0f}</b></td>
          <td style="text-align:center">{st_html}</td>
        </tr>"""
    rows += f"""<tr class="bom-total-row">
      <td colspan="4" style="text-align:right;padding-right:12px">QUOTE TOTAL ({currency_symbol.strip()})</td>
      <td style="text-align:right">{currency_symbol}{totals['total']:,.0f}</td>
      <td></td>
    </tr>"""
    return f"""
    <div style="overflow-x:auto">
    <table class="bom-table">
      <thead><tr>
        <th>SKU</th><th>DESCRIPTION</th><th>QTY</th>
        <th style="text-align:right">UNIT</th>
        <th style="text-align:right">TOTAL</th>
        <th style="text-align:center">STATUS</th>
      </tr></thead>
      <tbody>{rows}</tbody>
    </table>
    </div>"""


def render_audit(audit: dict) -> str:
    objections = audit.get("objections", [])
    if not objections:
        return '<div class="audit-item resolved"><span class="audit-issue">✓ No compatibility or compliance issues found.</span></div>'
    html = ""
    for obj in objections:
        sev = obj.get("severity", "")
        resolved = sev == "BLOCKING"
        cls = "resolved" if resolved else ("warning" if sev == "WARNING" else "")
        res_badge = '<span class="audit-resolved-badge">✓ RESOLVED</span>' if resolved else ""
        html += f"""
        <div class="audit-item {cls}">
          {res_badge}
          <div class="audit-sku">{obj.get('component_sku','N/A')}</div>
          <div class="audit-issue">{obj.get('issue','')}</div>
          <div class="audit-action">→ {obj.get('required_action','')}</div>
        </div>"""
    return html

def render_hero(timer_val):
    return f"""
    <div class="hero-grid">
      <div class="hero-left">
        <div class="hero-label">VERTICALIZED AGENTIC FRAMEWORK · 2026</div>
        <div class="hero-headline">
          Close the deal<br>before they <span>open the deck.</span>
        </div>
        <div class="hero-sub">
          Paste a raw RFQ. Watch three agents debate, catch compatibility errors a human would miss,
          and drop a legally valid quote into Salesforce — backed by Gemini.
        </div>
        <div class="hero-watermark">△</div>
      </div>
      <div class="hero-right">
        <div class="timer-label">// QUOTE GENERATION TIME</div>
        <div class="timer-value">{timer_val}</div>
        <div class="timer-compare">vs. average: <span>9 days</span></div>
      </div>
    </div>
    """

# ─────────────────────────────────────────────────────────────────────────────
# NAV BAR
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("""
<div class="nav-bar">
  <div class="nav-logo">
    <div class="nav-logo-box">AP</div>
    <span class="nav-title">AGROPILOT</span>
    <span class="nav-version">V3.0 (AI FULL-STACK)</span>
  </div>
  <div class="nav-env">
    <span class="env-dot"></span>
    GEMINI LIVE ENVIRONMENT
  </div>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# COMPLETION SCREEN — shown after approval
# ─────────────────────────────────────────────────────────────────────────────

if st.session_state.get("approved") and st.session_state.final_state:
    fs      = st.session_state.final_state
    hitl    = fs.get("hitl", {})
    elapsed = st.session_state.elapsed
    parsed  = fs.get("parsed_rfq", {})
    audit   = fs.get("compliance", {})
    blocking = [o for o in audit.get("objections", []) if o.get("severity") == "BLOCKING"]
    dispatch = st.session_state.get("dispatch_result", {})

    raw_location = parsed.get('farm_location') or 'Story County, Iowa, USA'
    location_parts = raw_location.split(',')
    region_display = location_parts[-1].strip() if location_parts else raw_location
    curr_sym = parsed.get("currency_symbol", hitl.get("currency_symbol", "$"))

    # Build action badges dynamically from real dispatch results
    completed = dispatch.get("actions_completed", [])
    failed    = dispatch.get("actions_failed", [])

    ACTION_LABELS = {
        "salesforce_create_opportunity": "SALESFORCE CREATED",
        "docusign_send_envelope":        "DOCUSIGN SENT",
        "slack_notify_manager":          "SLACK NOTIFIED",
        "gmail_send_quote":              "QUOTE EMAILED",
    }

    badges_html = ""
    for action_key, label in ACTION_LABELS.items():
        if any(action_key in c for c in completed):
            badges_html += f'<div class="action-badge">✓ {label}</div>'
        elif any(action_key in f for f in failed):
            badges_html += f'<div class="action-badge" style="border-color:#f43f5e;color:#fda4af;">⚠ {label} (failed)</div>'
        else:
            badges_html += f'<div class="action-badge" style="opacity:0.4">— {label} (skipped)</div>'

    sf_url = dispatch.get("salesforce_url", "")
    sf_link = f'<a href="{sf_url}" target="_blank" style="color:#818cf8;font-size:12px;">View in Salesforce →</a>' if sf_url else ""

    st.markdown(f"""
    <div class="completion-screen">
      <div class="completion-check">✓</div>
      <div class="completion-title">Quote Sent. Deal in Motion.</div>
      <div class="completion-sub">
        Total elapsed agent time: <span class="green">{fmt_time(elapsed)}</span>
        &nbsp;|&nbsp; Manual equivalent: <span class="red">9 days</span>
      </div>
      <div class="completion-actions">{badges_html}</div>
      {sf_link}
      <div class="completion-stats">
        <div class="stat">
          <div class="stat-label">Client Region</div>
          <div class="stat-value green">{region_display}</div>
        </div>
        <div class="stat">
          <div class="stat-label">Errors Caught</div>
          <div class="stat-value yellow">{len(blocking)} Resolved</div>
        </div>
        <div class="stat">
          <div class="stat-label">Total Value Secured</div>
          <div class="stat-value white">{curr_sym}{hitl.get('quote_total',0):,.0f}</div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # Fetch dispatch from session state safely so it always exists
    dispatch = st.session_state.get("dispatch_result", {})

    if dispatch.get("summary"):
        st.markdown(
            f"<div style='font-size:13px;color:#64748b;text-align:center;margin-top:-16px;padding-bottom:16px;'>"
            f"Agent: {dispatch['summary']}</div>",
            unsafe_allow_html=True
        )

    if st.button("↺  RUN AGAIN", key="run_again"):
        for k in ["approved","pipeline_done","final_state","elapsed","all_logs","dispatch_result"]:
            if k in st.session_state:
                del st.session_state[k]
        st.rerun()
    st.stop()

# ─────────────────────────────────────────────────────────────────────────────
# HERO SECTION (LIVE RENDER SLOT)
# ─────────────────────────────────────────────────────────────────────────────

hero_slot = st.empty()
timer_val = fmt_time(st.session_state.elapsed) if st.session_state.pipeline_done else "--:--"
hero_slot.markdown(render_hero(timer_val), unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# RFQ INPUT & INBOX LOADER
# ─────────────────────────────────────────────────────────────────────────────

with st.container():
    st.markdown("<div style='padding: 0 32px 12px'>", unsafe_allow_html=True)

    # Initialize the session state text variable if it doesn't exist yet
    if "rfq_text" not in st.session_state:
        st.session_state.rfq_text = ""

    if st.button("⚡ TRY SAMPLE RFQ", type="primary", use_container_width=True):
        st.session_state.rfq_text = DEMO_RFQ
        st.session_state.run_sample_rfq = True
        st.rerun()

    st.caption("Instant demo: runs a realistic sample RFQ locally. No account, API key, or external action is required.")

    with st.expander("📥 Load RFQ from Gmail inbox", expanded=False):
        st.markdown(
            "<div style='color:#94a3b8;font-size:13px;margin-bottom:10px'>"
            "Reads your latest matching email via Gmail API and loads it into the RFQ input."
            "</div>",
            unsafe_allow_html=True,
        )
        col_q, col_btn2 = st.columns([3, 1])
        with col_q:
            gmail_query = st.text_input(
                "Gmail search query",
                value='in:inbox newer_than:14d',
                help='Examples: `from:dealer@example.com`, `subject:RFQ`, `newer_than:7d`',
            )
        with col_btn2:
            load_gmail = st.button("Load latest", use_container_width=True)

        if load_gmail:
            token_path = os.getenv("GMAIL_TOKEN_PATH", os.path.join(os.path.dirname(__file__), "config", "token_gmail.json"))
            with st.spinner("Fetching latest email from Gmail..."):
                result = gmail_fetch_latest_rfq(gmail_query, token_path=token_path)
            if result.get("success"):
                header = f"FROM: {result.get('from','')}\nSUBJECT: {result.get('subject','')}\nDATE: {result.get('date','')}\n\n"
                st.session_state.rfq_text = (header + (result.get("body") or "")).strip()
                st.success("Loaded latest matching email into RFQ input.")
                st.rerun()
            else:
                st.error(result.get("error", "Failed to fetch Gmail message."))

        if st.button("Clear Text Area", use_container_width=True):
            st.session_state.rfq_text = ""
            st.rerun()

    # The remaining standalone input text area
    rfq = st.text_area(
        "RFQ Email",
        value=st.session_state.rfq_text,
        height=240,  # Slightly bumped height since the selector is gone
        label_visibility="collapsed",
        placeholder="Paste dealer RFQ email here...",
    )
    BASE_DIR = pathlib.Path(__file__).resolve().parent
    ENV_PATH = BASE_DIR / "config" / ".env"
    load_dotenv(dotenv_path=ENV_PATH)

    col_btn, col_status = st.columns([1, 3])
    with col_btn:
        run_clicked = st.button(
            "▶  RUN PIPELINE",
            type="primary",
            use_container_width=True,
            disabled=not rfq.strip(),
        )
        if st.session_state.pop("run_sample_rfq", False):
            run_clicked = True
    with col_status:
        if not os.getenv("GOOGLE_API_KEY"):
            st.markdown("<div style='color:#fbbf24;font-size:13.5px;padding-top:10px;font-weight:600;'>DEMO MODE · no API keys or external services are used</div>", unsafe_allow_html=True)
        elif st.session_state.pipeline_done:
            st.markdown("<div style='color:#7ee787;font-size:13.5px;padding-top:10px;font-weight:600;'>✓ Pipeline complete — scroll down to review and approve</div>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# PIPELINE RENDER SPACE (PERSISTENT LAYOUT GRID)
# ─────────────────────────────────────────────────────────────────────────────

pipeline_bar_slot = st.empty()

st.markdown("<div class='main-grid'>", unsafe_allow_html=True)
col_left, col_right = st.columns(2, gap="medium")

with col_left:
    rfq_badge_slot = st.empty()
    log_slot       = st.empty()

with col_right:
    bom_panel_header_slot = st.empty()
    bom_content_slot      = st.empty()
    st.markdown("</div></div>", unsafe_allow_html=True) # close panel tags safely
    
    audit_panel_header_slot = st.empty()
    audit_content_slot      = st.empty()
    st.markdown("</div></div>", unsafe_allow_html=True) # close panel tags safely

# Determine active state variant layout mapping
current_state = st.session_state.final_state if st.session_state.pipeline_done else None

# Set up defaults for empty or post-execution environments
rfq_preview = rfq[:600].replace("<","&lt;").replace(">","&gt;") if rfq else ""
bom = current_state.get("bom", []) if current_state else []
audit = current_state.get("compliance", {}) if current_state else {}
logs = st.session_state.all_logs if st.session_state.all_logs else []
cleared = current_state.get("compliance_cleared", False) if current_state else False
parsed_meta = current_state.get("parsed_rfq", {}) if current_state else {}
curr_sym = parsed_meta.get("currency_symbol", "$")

# Render static panel structure base configurations
pipeline_bar_slot.markdown(render_pipeline_bar("node_generate_quote" if st.session_state.pipeline_done else ""), unsafe_allow_html=True)

rfq_badge_slot.markdown(f"""
<div class="panel" style="margin-bottom:16px">
  <div class="panel-header">
    <span class="panel-title">📧 INBOUND RFQ</span>
    <span class="panel-badge {'badge-parsed' if st.session_state.pipeline_done else 'badge-awaiting'}">{'✓ PARSED' if st.session_state.pipeline_done else '⏳ IDLE'}</span>
  </div>
  <div class="panel-body">
    <div class="rfq-text">{rfq_preview if rfq_preview else 'No RFQ selected.'}</div>
  </div>
</div>
""", unsafe_allow_html=True)

log_slot.markdown(f"""
<div class="panel">
  <div class="panel-header">
    <span class="panel-title">⚡ AGENT SWARM</span>
    <span class="panel-badge {'badge-final' if st.session_state.pipeline_done else 'badge-awaiting'}">{'✓ COMPLETE' if st.session_state.pipeline_done else '⏳ IDLE'}</span>
  </div>
  <div class="panel-body" style="max-height:300px;overflow-y:auto">
    {render_log(logs)}
  </div>
</div>
""", unsafe_allow_html=True)

tots = _calculate_totals(bom) if bom else {"subtotal":0,"delivery":0,"taxes":0,"total":0}

# Fix display layout bugs by rendering headers & structural contents as isolated elements
bom_panel_header_slot.markdown(f"""
<div class="panel" style="margin-bottom:16px; padding-bottom:0px; border-bottom:none;">
  <div class="panel-header">
    <span class="panel-title">📋 BILL OF MATERIALS</span>
    <span class="panel-badge {'badge-final' if cleared else 'badge-awaiting'}">{'✓ FINAL' if cleared else '⏳ IDLE'}</span>
  </div>
  <div class="panel-body" style="padding-bottom:0px;">
""", unsafe_allow_html=True)
bom_content_slot.markdown(render_bom_table(bom, tots, curr_sym), unsafe_allow_html=True)

audit_panel_header_slot.markdown(f"""
<div class="panel" style="padding-bottom:0px; border-bottom:none;">
  <div class="panel-header">
    <span class="panel-title">🛡️ AUDIT PROTOCOL</span>
    <span class="panel-badge {'badge-cleared' if cleared else 'badge-awaiting'}">{'✓ CLEARED' if cleared else '⏳ IDLE'}</span>
  </div>
  <div class="panel-body" style="padding-bottom:0px;">
""", unsafe_allow_html=True)
audit_content_slot.markdown(render_audit(audit), unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# PIPELINE STREAM PROCESSING ENGINE
# ─────────────────────────────────────────────────────────────────────────────

if run_clicked and rfq.strip():
    st.session_state.pipeline_done = False
    st.session_state.final_state   = None
    st.session_state.all_logs      = []
    st.session_state.elapsed       = 0
    if "approved" in st.session_state:
        del st.session_state["approved"]

    graph = build_graph()
    initial: QuoteState = {
        "rfq_email":          rfq,
        "parsed_rfq":         {},
        "bom":                [],
        "compliance":         {},
        "sentinel":           {},
        "debate_round":       0,
        "max_debate_rounds":  3,
        "compliance_cleared": False,
        "final_quotation":    "",
        "hitl":               {},
        "log":                [],
    }

    rfq_badge_slot.markdown(f"""
    <div class="panel" style="margin-bottom:16px">
      <div class="panel-header">
        <span class="panel-title">📧 INBOUND RFQ</span>
        <span class="panel-badge badge-awaiting">⏳ PROCESSING</span>
      </div>
      <div class="panel-body">
        <div class="rfq-text">{rfq_preview}</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    NODE_STAGE = {
        "node_parse":          "node_parse",
        "node_configurator":   "node_configurator",
        "node_critic":         "node_critic",
        "node_sentinel":       "node_sentinel",
        "node_generate_quote": "node_generate_quote",
    }

    start_time  = time.time()
    accumulated_state = dict(initial)

    # ── Background worker streams graph steps into a queue ──────────────────
    def _graph_worker(g, init, q):
        try:
            for s in g.stream(init):
                q.put(("step", s))
            q.put(("done", None))
        except Exception as e:
            q.put(("error", e))

    _q = queue.Queue()
    _t = threading.Thread(target=_graph_worker, args=(graph, initial, _q), daemon=True)
    _t.start()

    # ── Main thread: tick timer every 0.5 s, render on each new step ─────────
    try:
        while _t.is_alive() or not _q.empty():
            # Always update the timer
            elapsed = int(time.time() - start_time)
            st.session_state.elapsed = elapsed
            hero_slot.markdown(render_hero(fmt_time(elapsed)), unsafe_allow_html=True)

            # Drain all queued steps that arrived since last tick
            while True:
                try:
                    kind, data = _q.get_nowait()
                except queue.Empty:
                    break

                if kind == "error":
                    raise data
                if kind == "done":
                    continue

                # kind == "step"
                node_name  = list(data.keys())[0]
                node_state = data[node_name]

                for key, val in node_state.items():
                    if key == "log":
                        accumulated_state["log"] = accumulated_state.get("log", []) + val
                    else:
                        accumulated_state[key] = val

                pipeline_bar_slot.markdown(
                    render_pipeline_bar(NODE_STAGE.get(node_name, "")),
                    unsafe_allow_html=True,
                )

                all_logs = accumulated_state["log"]
                st.session_state.all_logs = all_logs

                swarm_badge = "badge-awaiting" if node_name != "node_generate_quote" else "badge-final"
                swarm_label = "⏳ AWAITING" if node_name != "node_generate_quote" else "✓ COMPLETE"

                log_slot.markdown(f"""
                <div class="panel">
                  <div class="panel-header">
                    <span class="panel-title">⚡ AGENT SWARM</span>
                    <span class="panel-badge {swarm_badge}">{swarm_label}</span>
                  </div>
                  <div class="panel-body" style="max-height:300px;overflow-y:auto">
                    {render_log(all_logs)}
                  </div>
                </div>
                """, unsafe_allow_html=True)

                if node_name != "node_parse":
                    rfq_badge_slot.markdown(f"""
                    <div class="panel" style="margin-bottom:16px">
                      <div class="panel-header">
                        <span class="panel-title">📧 INBOUND RFQ</span>
                        <span class="panel-badge badge-parsed">✓ PARSED</span>
                      </div>
                      <div class="panel-body">
                        <div class="rfq-text">{rfq_preview}</div>
                      </div>
                    </div>
                    """, unsafe_allow_html=True)

                parsed_meta = accumulated_state.get("parsed_rfq", {})
                curr_sym = parsed_meta.get("currency_symbol", "$")

                bom  = accumulated_state.get("bom", [])
                tots = _calculate_totals(bom) if bom else {"subtotal":0,"delivery":0,"taxes":0,"total":0}
                bom_badge = "badge-final" if accumulated_state.get("compliance_cleared") else "badge-awaiting"
                bom_label = "✓ FINAL" if accumulated_state.get("compliance_cleared") else "⏳ DRAFT"

                bom_panel_header_slot.markdown(f"""
                <div class="panel" style="margin-bottom:16px; padding-bottom:0px; border-bottom:none;">
                  <div class="panel-header">
                    <span class="panel-title">📋 BILL OF MATERIALS</span>
                    <span class="panel-badge {bom_badge}">{bom_label}</span>
                  </div>
                  <div class="panel-body" style="padding-bottom:0px;">
                """, unsafe_allow_html=True)
                bom_content_slot.markdown(render_bom_table(bom, tots, curr_sym), unsafe_allow_html=True)

                audit = accumulated_state.get("compliance", {})
                cleared = accumulated_state.get("compliance_cleared", False)
                audit_badge = "badge-cleared" if cleared else "badge-awaiting"
                audit_label = "✓ CLEARED" if cleared else "⏳ AUDITING"

                audit_panel_header_slot.markdown(f"""
                <div class="panel" style="padding-bottom:0px; border-bottom:none;">
                  <div class="panel-header">
                    <span class="panel-title">🛡️ AUDIT PROTOCOL</span>
                    <span class="panel-badge {audit_badge}">{audit_label}</span>
                  </div>
                  <div class="panel-body" style="padding-bottom:0px;">
                """, unsafe_allow_html=True)
                audit_content_slot.markdown(render_audit(audit), unsafe_allow_html=True)

            time.sleep(0.5)   # yield for 0.5 s then tick timer again

    except Exception as exc:
        st.error(f"Pipeline error: {exc}")
        st.exception(exc)
        st.stop()

    st.session_state.pipeline_done = True
    st.session_state.final_state   = accumulated_state
    st.session_state.elapsed       = int(time.time() - start_time)

    pipeline_bar_slot.markdown(render_pipeline_bar("node_generate_quote"), unsafe_allow_html=True)
    st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# HITL APPROVAL PANEL — shown after pipeline completes
# ─────────────────────────────────────────────────────────────────────────────

if st.session_state.pipeline_done and st.session_state.final_state:
    fs      = st.session_state.final_state
    hitl    = fs.get("hitl", {})
    sentinel= fs.get("sentinel", {})
    bom     = fs.get("bom", [])
    totals  = _calculate_totals(bom)

    parsed_meta = fs.get("parsed_rfq", {})
    curr_sym = parsed_meta.get("currency_symbol", hitl.get("currency_symbol", "$"))

    quote_total = totals.get("total", 0) or hitl.get("quote_total", 0)
    margin      = sentinel.get("gross_margin_pct", 0) or hitl.get("gross_margin_pct", 0)
    win_prob    = sentinel.get("win_probability_pct", 0) or hitl.get("win_probability_pct", 0)
    win_lvl     = sentinel.get("win_level", hitl.get("win_level", "MED"))
    blocking_ct = hitl.get("blocking_resolved", 0)
    rounds      = fs.get("debate_round", hitl.get("debate_rounds", 1))
    rationale   = sentinel.get("deal_rationale", hitl.get("rationale", ""))
    rec         = sentinel.get("recommendation", hitl.get("recommendation", "APPROVE AS-IS"))
    upsell      = sentinel.get("upsell_opportunity", hitl.get("upsell", ""))
    dealer      = hitl.get("dealer_company", "N/A")
    contact     = hitl.get("dealer_contact", "N/A")
    farmer      = hitl.get("farm_operator", "N/A")
    equipment   = hitl.get("equipment", "N/A")
    rfq_id      = hitl.get("rfq_id", "AQ-2026-0000")

    rec_color = "#00ff87" if "APPROVE" in rec else ("#fbbf24" if "NEGOTIATE" in rec else "#f43f5e")

    st.markdown(f"""
    <div class="hitl-panel">
      <div class="hitl-title">✅ DEALER APPROVAL — HUMAN-IN-THE-LOOP</div>
      <div class="hitl-metrics">
        <div class="hitl-metric">
          <div class="hitl-metric-label">Deal Value</div>
          <div class="hitl-metric-value white">{curr_sym}{quote_total:,.0f}</div>
        </div>
        <div class="hitl-metric">
          <div class="hitl-metric-label">Gross Margin</div>
          <div class="hitl-metric-value green">{margin:.1f}%</div>
        </div>
        <div class="hitl-metric">
          <div class="hitl-metric-label">Win Probability</div>
          <div class="hitl-metric-value green">{win_prob}%</div>
        </div>
        <div class="hitl-metric">
          <div class="hitl-metric-label">Issues Resolved</div>
          <div class="hitl-metric-value yellow">{blocking_ct}</div>
        </div>
        <div class="hitl-metric">
          <div class="hitl-metric-label">Config Rounds</div>
          <div class="hitl-metric-value white">{rounds}</div>
        </div>
      </div>
      <div class="hitl-rationale">{rationale or 'Agent analysis complete.'}</div>
      {"<div style='font-size:13.5px;color:#a5b4fc;margin-bottom:14px;font-weight:600;'>💡 Recommended Upsell Strategy: " + upsell + "</div>" if upsell else ""}
      <div style='font-size:14px;font-weight:800;color:{rec_color};margin-bottom:16px;letter-spacing:.08em;text-transform:uppercase;'>
        RECOMMENDATION: {rec}
      </div>
    </div>
    """, unsafe_allow_html=True)

    quotation = fs.get("final_quotation", "")
    if quotation:
        with st.expander("📄 View full quotation document"):
            st.code(quotation, language=None)
        st.download_button(
            "⬇️ Download Quotation (.txt)",
            data=quotation,
            file_name=f"AgriQuote_{rfq_id}.txt",
            mime="text/plain",
        )

    col_a, col_b = st.columns(2)
    with col_a:
        demo_mode = os.getenv("AGROPILOT_DEMO_MODE", "").strip().lower() in {"1", "true", "yes", "on"}
        live_dispatch_enabled = bool(os.getenv("GOOGLE_API_KEY")) and not demo_mode
        if st.button("✅  APPROVE & SUBMIT CONFIGURATION", type="primary", use_container_width=True, disabled=not live_dispatch_enabled):
            with st.spinner("🤖 Agent dispatching downstream actions..."):
                from mcp_architecture.mcp_agent import run_post_approval_agent
                dispatch_result = run_post_approval_agent(st.session_state.final_state, max_iterations=20)
                st.session_state.dispatch_result = dispatch_result
            st.session_state.approved = True
            st.rerun()
        if not live_dispatch_enabled:
            st.caption("Demo safety: downstream CRM, email, signature, and Slack actions are disabled.")
    with col_b:
        if st.button("✏️  EDIT RFQ", use_container_width=True):
            st.session_state.pipeline_done = False
            st.session_state.final_state = None
            st.session_state.elapsed = 0
            st.session_state.all_logs = []
            st.rerun()
