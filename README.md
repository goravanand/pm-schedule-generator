# 🔧 AI PM Schedule Generator

An AI-powered prototype that reads maintenance documents (PDFs) or voice transcripts
and automatically generates pre-populated Preventive Maintenance (PM) schedules
for the MMM PM Creation Form in Asset Essentials.

Built for **AR-952 — AI PM Schedule Generation** (Epic: AR-121 Trinity MMM Mid-Market AI).

---

## What it does

- Upload a **PDF** (OEM manual, maintenance SOP, inspection guide)
  or paste a **voice transcript / text description**
- AI classifies the document and extracts all 10 MMM PM Creation Form fields
- Results displayed as an editable form — review, adjust, then **Create** or **Discard** each PM
- Handles multiple frequencies (monthly + annual = 2 separate PMs)
- Flags missing frequencies and zero-PM documents automatically

---

## 10 MMM Fields Extracted

| # | Field | Type |
|---|---|---|
| 1 | Assets | Mandatory (always blank — user selects in MMM) |
| 2 | Title | Mandatory |
| 3 | Category | Mandatory (9 fixed values) |
| 4 | Repeats | Mandatory |
| 5 | Start On | Mandatory |
| 6 | Create WO Time | Mandatory |
| 7 | End After | Optional |
| 8 | Assign To | Optional |
| 9 | Description | Optional (max 2,000 chars) |
| 10 | Add Attachment | Optional |

---

## Running locally

```bash
pip install streamlit anthropic pdfplumber
streamlit run app.py
```

Enter your Claude API key in the sidebar when prompted.

---

## Deploying to Streamlit Cloud

1. Fork or clone this repo to your GitHub account
2. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub
3. Click **New app** → select this repo → `app.py`
4. Under **Advanced settings → Secrets**, add:

```toml
ANTHROPIC_API_KEY = "your-key-here"
```

5. Click **Deploy** — live URL generated in ~2 minutes

---

## Document types supported

| Type | Example | PMs Generated | Confidence |
|---|---|---|---|
| OEM Manual | Trane RT-SVX37C-EN | 2–5 | High |
| Maintenance SOP | GMP SOP-04 | 1–3 | Medium |
| Breakdown SOP | Reactive repair guide | 0 | — |
| Other | Inspection report | Attempted | Low |

---

*Prototype for AR-952 validation — Brightly / Siemens, 2026*
