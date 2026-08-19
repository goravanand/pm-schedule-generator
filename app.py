import streamlit as st
import anthropic
import pdfplumber
import json
from datetime import datetime, date

# ── Page config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AI PM Schedule Generator",
    page_icon="🔧",
    layout="wide"
)

# ── CSS — form styling ───────────────────────────────────────────────────────
st.markdown("""
<style>
/* AI suggestion caption */
.ai-badge {
    font-size: 0.78rem;
    color: #6b7280;
    font-style: italic;
    margin-top: -8px;
    margin-bottom: 6px;
}
/* Field label */
.field-label {
    font-weight: 600;
    font-size: 0.92rem;
    margin-bottom: 2px;
}
/* Section header */
.section-header {
    font-size: 1.05rem;
    font-weight: 700;
    color: #1e40af;
    border-bottom: 2px solid #dbeafe;
    padding-bottom: 4px;
    margin-top: 16px;
    margin-bottom: 10px;
}
</style>
""", unsafe_allow_html=True)

# ── Constants ────────────────────────────────────────────────────────────────
CATEGORY_OPTIONS = [
    "Calibration",
    "Cleaning/Sanitation",
    "Compliance",
    "Inspection",
    "Other",
    "Preventive Maintenance",
    "Process Improvement",
    "Projects",
    "Safety",
]

# ── System prompt ────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """
You are an AI assistant specialised in extracting Preventive Maintenance (PM)
schedules from maintenance documents, OEM equipment manuals, Standard Operating
Procedures (SOPs), and voice transcripts.

Your sole job is to read the provided content and populate the MMM PM Creation
Form — 10 fields total (6 mandatory, 4 optional).

════════════════════════════════════════════════════
SECTION 1 — CLASSIFY THE DOCUMENT FIRST
════════════════════════════════════════════════════

Classify into one of:

  TYPE A — OEM Equipment Manual
    Manufacturer-published manual. Contains explicit calendar frequencies.
    Expected: HIGH confidence. Usually 2–5 distinct PMs.

  TYPE B — Internal Maintenance SOP
    Organisation's own procedure. Describes WHAT and HOW but may not state
    HOW OFTEN.
    Expected: MEDIUM confidence. Usually 1–3 PMs. Frequency gap likely.

  TYPE C — Breakdown / Reactive Maintenance SOP
    Triggered ONLY when equipment has already failed. No calendar schedule.
    Expected: ZERO PMs. Do NOT generate a PM.

  TYPE D — Other
    Commissioning, warranty, parts catalogue, inspection report.
    Expected: Attempt extraction. Flag uncertainty. Low confidence.

════════════════════════════════════════════════════
SECTION 2 — IDENTIFY SCHEDULABLE ACTIVITIES
════════════════════════════════════════════════════

INCLUDE (schedulable):
  ✅ Tasks with explicit calendar frequency (daily, weekly, monthly, annual)
  ✅ Tasks with time intervals (every 3 months, every 6 months, every 2 years)
  ✅ Tasks under headings: Scheduled/Preventive/Routine/Periodic Maintenance
  ✅ Tasks described as "should be done regularly" — flag frequency gap but
     still extract

EXCLUDE (not schedulable):
  ❌ Breakdown or corrective tasks (triggered by failure)
  ❌ Commissioning tasks (one-time, at installation only)
  ❌ Event-triggered tasks (e.g. "check belt 2–3 days after installation")
  ❌ Conditional tasks (e.g. "replace filter IF pressure drops")
  ❌ Administrative procedures (approval flows, sign-off processes)

FREQUENCY RULE — One PM per distinct frequency:
  Monthly tasks   → PM #1
  Annual tasks    → PM #2
  Quarterly tasks → PM #3

════════════════════════════════════════════════════
SECTION 3 — THE 10 PM CREATION FORM FIELDS
════════════════════════════════════════════════════

For EACH schedulable frequency group, populate ALL 10 fields:

MANDATORY FIELD 1 — Assets
  Rule:  ALWAYS leave blank. Never auto-populate.
  Value: "❌ Not auto-populated — user selects manually in MMM"

MANDATORY FIELD 2 — Title
  Rule:  Clear descriptive title.
  Format: [Task Type] — [Equipment Name or Category]
  Good:  "Monthly Preventive Maintenance Inspection — Trane Rooftop Unit"
  Bad:   "PM" or "Maintenance" (too vague)

MANDATORY FIELD 3 — Category
  Rule:  Select EXACTLY ONE from these 9 values only:
    Calibration | Cleaning/Sanitation | Compliance | Inspection |
    Other | Preventive Maintenance | Process Improvement | Projects | Safety

  Guidance:
    Check filters, inspect belts, verify thermostat  → Inspection
    Clean coils, flush drain pan                     → Cleaning/Sanitation
    Lubricate bearings, replace worn parts           → Preventive Maintenance
    Calibrate gauges, test instruments               → Calibration
    OSHA-required check                              → Compliance

MANDATORY FIELD 4 — Repeats
  Rule:  Extract exact frequency from document.
  Format: "[Frequency] — Every [N] [Unit], [Day/Date]"

  Smart defaults when day/date not stated:
    Daily    → "Daily — Every 1 Day"
    Weekly   → "Weekly — Every 1 Week, Sunday"
    Monthly  → "Monthly — Every 1 Month, 1st of the month"
    Yearly   → "Yearly — Every 1 Year, January 1st"
    Quarterly → "Every 3 Months, 1st of the month"

MANDATORY FIELD 5 — Start On
  Rule:  Use today's date from TODAY_DATE provided below.

MANDATORY FIELD 6 — Create WO Time
  Rule:  Use current time from CURRENT_TIME provided below.

OPTIONAL FIELD 7 — End After
  Rule:  Populate ONLY if document states an explicit end condition.
  Default: "Blank"

OPTIONAL FIELD 8 — Assign To
  Rule:  Populate ONLY if a specific technician or named role is stated.
  Default: "Blank"
  Do NOT use generic phrases like "qualified personnel" or "maintenance staff".

OPTIONAL FIELD 9 — Description
  Rule:  Extract full task checklist. Maximum 2000 characters.
  Priority order if truncation needed:
    1. Safety warnings and PPE requirements (always include)
    2. Critical operational tasks
    3. Inspection / check items
    4. Record-keeping steps (shorten or omit if needed)
  Structure:
    Line 1:  ⚠️ SAFETY / PPE — [requirements]
    Lines 2+: Numbered task list verbatim from document
    Last:    Compliance notes / source reference

OPTIONAL FIELD 10 — Add Attachment
  Rule:  Always recommend attaching the source document.
  Value: "Attach source document: [SOURCE_NAME]"

════════════════════════════════════════════════════
SECTION 4 — SPECIAL HANDLING RULES
════════════════════════════════════════════════════

RULE A — Frequency Gap (no frequency stated)
  Set frequency_gap = true
  Set repeats = "⚠️ Not specified in document — user must set frequency"
  Still create the PM with all other fields populated.
  Explain in frequency_gap_note what was found and what user must decide.

RULE B — Zero PM (purely reactive document)
  Set pm_count = 0
  Set no_pm_reason = clear explanation
  Return empty pms array: []
  Do NOT force-fit a breakdown procedure into a PM.

RULE C — Mixed document
  Extract ONLY the preventive/scheduled sections.
  Exclude reactive/breakdown sections.
  Note what was excluded in confidence_reason.

RULE D — Compliance reference detected
  Note detected agency in compliance_agencies_detected array.
  Do NOT create a separate Compliance Agency field (not yet in MMM).
  Flag it in confidence_reason.

════════════════════════════════════════════════════
SECTION 5 — CONFIDENCE SCORING
════════════════════════════════════════════════════

HIGH:
  ✅ OEM manual or specification-rich document
  ✅ Explicit calendar frequency found
  ✅ Task list clearly described
  ✅ Category unambiguous
  ✅ No significant extraction gaps

MEDIUM:
  ⚠️ Internal SOP — tasks clear, frequency unclear
  ⚠️ Frequency found but day/date defaulted
  ⚠️ Category required judgment
  ⚠️ Description condensed to fit 2000 chars

LOW:
  ❌ Scanned / image-based document
  ❌ Document type ambiguous
  ❌ Frequency entirely absent
  ❌ Tasks vaguely described

════════════════════════════════════════════════════
SECTION 6 — OUTPUT FORMAT
════════════════════════════════════════════════════

Return ONLY valid JSON. No markdown. No explanation outside the JSON.
No code blocks. Start with { and end with }.

{
  "document_type": "OEM Manual | Maintenance SOP | Breakdown SOP | Other",
  "ai_confidence": "High | Medium | Low",
  "confidence_reason": "One or two sentences",
  "compliance_agencies_detected": [],
  "pm_count": 0,
  "frequency_gap": false,
  "frequency_gap_note": "",
  "no_pm_reason": "",
  "pms": [
    {
      "pm_number": 1,
      "assets": "❌ Not auto-populated — user selects manually in MMM",
      "title": "",
      "category": "",
      "repeats": "",
      "start_on": "",
      "create_wo_time": "",
      "end_after": "Blank",
      "assign_to": "Blank",
      "description": "",
      "add_attachment": "",
      "description_char_count": 0,
      "extraction_notes": ""
    }
  ]
}
"""

# ── Helpers ──────────────────────────────────────────────────────────────────

def extract_pdf_text(uploaded_file):
    """Extract text from a PDF file using pdfplumber."""
    text = ""
    try:
        with pdfplumber.open(uploaded_file) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except Exception as e:
        st.error(f"Could not read PDF: {e}")
    return text.strip()


def call_claude(content, source_name, api_key):
    """Send content to Claude and return the raw JSON string."""
    client = anthropic.Anthropic(api_key=api_key)
    today  = date.today().strftime("%B %d, %Y")
    now    = datetime.now().strftime("%I:%M %p")

    user_msg = f"""TODAY_DATE   : {today}
CURRENT_TIME : {now}
SOURCE_NAME  : {source_name}

════════════════════════════════════════
CONTENT TO ANALYSE:
════════════════════════════════════════

{content}

════════════════════════════════════════

Extract all schedulable PM schedules from the above content.
Apply all rules from your instructions.
Return JSON only.
"""
    response = client.messages.create(
        model="sparkai-developer-claude",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}]
    )
    return response.content[0].text


def confidence_colour(level):
    colours = {"High": "🟢", "Medium": "🟡", "Low": "🔴"}
    return colours.get(level, "⚪")


def ai_caption(suggested_value):
    """Render a small AI-suggested caption below a field."""
    if suggested_value and suggested_value not in ("Blank", ""):
        st.markdown(
            f'<p class="ai-badge">🤖 AI suggested: {suggested_value}</p>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<p class="ai-badge">🤖 AI suggested: (none / left blank)</p>',
            unsafe_allow_html=True,
        )


# ── PM Form renderer ─────────────────────────────────────────────────────────

def render_pm_form(pm, freq_gap, freq_note, index, run_id):
    """
    Render one PM as an editable form.
    Each field shows the AI suggestion and lets the user change it.
    Create / Discard buttons at the bottom.
    """
    num        = pm.get("pm_number", index)
    key_prefix = f"run{run_id}_pm{num}"
    status_key = f"{key_prefix}_status"

    # Initialise status once
    if status_key not in st.session_state:
        st.session_state[status_key] = "pending"

    status = st.session_state[status_key]

    # ── Already acted on ──────────────────────────────────────────────
    if status == "created":
        saved_title = st.session_state.get(f"{key_prefix}_title", pm.get("title", f"PM #{num}"))
        st.success(f"✅  **PM #{num} — {saved_title}** created successfully.")
        return

    if status == "discarded":
        st.warning(f"🗑️  **PM #{num} — {pm.get('title', '')}** was discarded.")
        return

    # ── Pending — show editable form ──────────────────────────────────
    with st.container(border=True):

        # Header row
        h_col1, h_col2 = st.columns([8, 2])
        with h_col1:
            st.markdown(f"## 📋 PM #{num}")
        with h_col2:
            st.markdown("<br>", unsafe_allow_html=True)
            st.caption("🟡 Pending review")

        if freq_gap:
            st.warning(
                f"⚠️ **Frequency not stated in document.** {freq_note}  \n"
                "Please update the **Repeats** field below before creating this PM."
            )

        # ── MANDATORY FIELDS ──────────────────────────────────────────
        st.markdown('<p class="section-header">⭐ Mandatory Fields</p>', unsafe_allow_html=True)

        # 1 · Assets (always read-only)
        st.markdown("**🏢 Assets**")
        st.info("❌ Not auto-populated — you will select the asset(s) manually in MMM after creating this PM.")
        ai_caption("Leave blank — D25 decision")

        st.divider()

        # 2 · Title
        ai_title = pm.get("title", "")
        st.markdown("**📝 Title** *(mandatory)*")
        st.text_input(
            "Title",
            value=ai_title,
            key=f"{key_prefix}_title",
            label_visibility="collapsed",
            placeholder="Enter PM title…",
        )
        ai_caption(ai_title)

        # 3 · Category
        ai_cat  = pm.get("category", "Other")
        cat_idx = CATEGORY_OPTIONS.index(ai_cat) if ai_cat in CATEGORY_OPTIONS else 4
        st.markdown("**🏷️ Category** *(mandatory)*")
        st.selectbox(
            "Category",
            options=CATEGORY_OPTIONS,
            index=cat_idx,
            key=f"{key_prefix}_category",
            label_visibility="collapsed",
        )
        ai_caption(ai_cat)

        # 4 · Repeats
        ai_repeats  = pm.get("repeats", "")
        show_repeat = "" if "Not specified" in ai_repeats else ai_repeats
        st.markdown("**🔁 Repeats** *(mandatory)*")
        st.text_input(
            "Repeats",
            value=show_repeat,
            key=f"{key_prefix}_repeats",
            label_visibility="collapsed",
            placeholder="e.g. Monthly — Every 1 Month, 1st of the month",
        )
        ai_caption(ai_repeats)

        # 5 & 6 · Start On + Create WO Time (side by side)
        s_col1, s_col2 = st.columns(2)

        ai_start = pm.get("start_on", "")
        with s_col1:
            st.markdown("**📅 Start On** *(mandatory)*")
            st.text_input(
                "Start On",
                value=ai_start,
                key=f"{key_prefix}_start_on",
                label_visibility="collapsed",
            )
            ai_caption(ai_start)

        ai_wo = pm.get("create_wo_time", "")
        with s_col2:
            st.markdown("**⏰ Create WO Time** *(mandatory)*")
            st.text_input(
                "Create WO Time",
                value=ai_wo,
                key=f"{key_prefix}_create_wo_time",
                label_visibility="collapsed",
            )
            ai_caption(ai_wo)

        # ── OPTIONAL FIELDS ───────────────────────────────────────────
        st.markdown('<p class="section-header">🔵 Optional Fields</p>', unsafe_allow_html=True)

        o_col1, o_col2, o_col3 = st.columns(3)

        ai_end = pm.get("end_after", "Blank")
        with o_col1:
            st.markdown("**🔚 End After**")
            st.text_input(
                "End After",
                value="" if ai_end == "Blank" else ai_end,
                key=f"{key_prefix}_end_after",
                label_visibility="collapsed",
                placeholder="Leave blank if not applicable",
            )
            ai_caption(ai_end)

        ai_assign = pm.get("assign_to", "Blank")
        with o_col2:
            st.markdown("**👤 Assign To**")
            st.text_input(
                "Assign To",
                value="" if ai_assign == "Blank" else ai_assign,
                key=f"{key_prefix}_assign_to",
                label_visibility="collapsed",
                placeholder="Leave blank if not applicable",
            )
            ai_caption(ai_assign)

        ai_attach = pm.get("add_attachment", "")
        with o_col3:
            st.markdown("**📎 Add Attachment**")
            st.text_input(
                "Add Attachment",
                value=ai_attach,
                key=f"{key_prefix}_add_attachment",
                label_visibility="collapsed",
                placeholder="Attach source document…",
            )
            ai_caption(ai_attach)

        # ── DESCRIPTION ───────────────────────────────────────────────
        st.markdown('<p class="section-header">📄 Description</p>', unsafe_allow_html=True)

        ai_desc_raw = pm.get("description", "")
        # Hard-enforce 2,000 char limit — truncate AI output at 1,950 and add note
        if len(ai_desc_raw) > 2000:
            ai_desc = ai_desc_raw[:1950].rstrip() + "\n[Truncated to fit 2,000 character limit]"
        else:
            ai_desc = ai_desc_raw

        desc_val = st.text_area(
            "Description",
            value=ai_desc,
            height=260,
            key=f"{key_prefix}_description",
            label_visibility="collapsed",
            help="Edit the AI-generated task checklist. Maximum 2,000 characters.",
        )
        char_count = len(desc_val)
        char_icon  = "🟢" if char_count < 1600 else ("🟡" if char_count < 1900 else "🔴")
        ai_caption(f"{ai_desc_raw[:60]}…" if len(ai_desc_raw) > 60 else ai_desc_raw)
        st.caption(f"{char_icon} {char_count:,} / 2,000 characters used")
        if char_count > 2000:
            st.error(f"⚠️ Description still exceeds 2,000 characters by {char_count - 2000}. Please shorten before creating.")

        # ── AI Extraction notes ───────────────────────────────────────
        notes = pm.get("extraction_notes", "")
        if notes:
            st.info(f"📌 **AI Note:** {notes}")

        # ── ACTION BUTTONS ────────────────────────────────────────────
        st.divider()
        btn1, btn2, spacer = st.columns([2, 2, 6])

        with btn1:
            if st.button(
                "✅  Create PM",
                key=f"{key_prefix}_btn_create",
                type="primary",
                use_container_width=True,
                disabled=(char_count > 2000),
            ):
                st.session_state[status_key] = "created"
                st.rerun()

        with btn2:
            if st.button(
                "🗑️  Discard",
                key=f"{key_prefix}_btn_discard",
                type="secondary",
                use_container_width=True,
            ):
                st.session_state[status_key] = "discarded"
                st.rerun()


# ── Main app ─────────────────────────────────────────────────────────────────

def main():

    # ── Header ──────────────────────────────────────────────────────
    st.title("🔧 AI PM Schedule Generator")
    st.markdown(
        "Upload a maintenance document **or** paste a voice transcript → "
        "get a pre-populated PM schedule with all 10 MMM fields.  \n"
        "Review each field, edit where needed, then **Create** or **Discard** each PM."
    )
    st.divider()

    # ── Sidebar ──────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("### ⚙️ Setup")

        # Load from Streamlit secrets if pre-configured (deployed version)
        # Falls back to manual entry for local use
        try:
            secret_key = st.secrets.get("ANTHROPIC_API_KEY", "")
        except Exception:
            secret_key = ""

        if secret_key:
            api_key = secret_key
            st.success("✅ API key configured")
        else:
            api_key = st.text_input(
                "Claude API Key",
                type="password",
                placeholder="sk-ant-api03-…",
                help="Get your key at console.anthropic.com → API Keys"
            )
            if api_key:
                st.success("✅ API key entered")
            else:
                st.warning("⚠️ Enter your API key to enable generation")

        st.divider()

        st.markdown("#### 📊 What this prototype tests")
        st.markdown("""
- Can AI read a maintenance PDF?
- Does it extract the right 10 fields?
- Does it handle **missing frequency**?
- Does it produce **0 PMs** for a breakdown SOP?
- Does it create separate PMs per frequency?
        """)

        st.divider()

        st.markdown("#### 🏷️ Valid Category Values")
        for cat in CATEGORY_OPTIONS:
            st.markdown(f"• {cat}")

    # ── Input tabs ───────────────────────────────────────────────────
    tab_doc, tab_voice = st.tabs(["📄 Document Upload", "🎙️ Voice / Text Input"])

    with tab_doc:
        st.markdown("### Upload a Maintenance Document (PDF)")
        st.markdown(
            "Supports: OEM equipment manuals, maintenance SOPs, "
            "service guides, inspection procedures."
        )

        uploaded = st.file_uploader(
            "Choose a PDF file",
            type=["pdf"],
            label_visibility="collapsed"
        )

        if uploaded:
            st.success(f"✅ **{uploaded.name}** — {uploaded.size / 1024:.1f} KB")
            pdf_text = extract_pdf_text(uploaded)

            if pdf_text:
                with st.expander(f"📖 Preview extracted text ({len(pdf_text):,} characters)"):
                    st.text_area(
                        "",
                        value=pdf_text[:3000] + ("…" if len(pdf_text) > 3000 else ""),
                        height=200,
                        disabled=True,
                    )
            else:
                st.error(
                    "⚠️ No text could be extracted. This may be a scanned / "
                    "image-based PDF. Try a text-based PDF for best results."
                )

            clicked = st.button(
                "🚀 Generate PM Schedules",
                key="go_pdf",
                type="primary",
                disabled=(not api_key or not pdf_text),
            )

            if clicked:
                with st.spinner("Analysing document and extracting PM schedules…"):
                    raw = call_claude(pdf_text, uploaded.name, api_key)
                    st.session_state["result"]  = raw
                    st.session_state["source"]  = uploaded.name
                    st.session_state["run_id"]  = st.session_state.get("run_id", 0) + 1

    with tab_voice:
        st.markdown("### Paste Voice Transcript or Type a Description")
        st.info(
            "💡 **How to use voice input:**  \n"
            "1. Open any voice-to-text app on your phone or computer  \n"
            "   *(Windows: Win + H → Windows Voice Typing)*  \n"
            "2. Speak your maintenance requirements  \n"
            "3. Copy the transcript and paste it below"
        )

        voice_text = st.text_area(
            "Voice transcript or maintenance description",
            placeholder=(
                "Example:\n\n"
                "We need a monthly inspection of the HVAC units on the 1st of each month. "
                "Tasks include checking filters, lubricating fan bearings, inspecting belts "
                "for wear, and verifying thermostat calibration.\n\n"
                "We also need an annual coil cleaning every January — clean condenser and "
                "evaporator coils, apply corrosion inhibitor, check refrigerant levels."
            ),
            height=260,
        )

        src_label = st.text_input(
            "Source label (optional)",
            placeholder="e.g., Site Manager verbal briefing",
            value="Voice Input",
        )

        clicked_voice = st.button(
            "🚀 Generate PM Schedules",
            key="go_voice",
            type="primary",
            disabled=(not api_key or not voice_text.strip()),
        )

        if clicked_voice:
            with st.spinner("Analysing input and extracting PM schedules…"):
                raw = call_claude(voice_text, src_label or "Voice Input", api_key)
                st.session_state["result"]  = raw
                st.session_state["source"]  = src_label or "Voice Input"
                st.session_state["run_id"]  = st.session_state.get("run_id", 0) + 1

    # ── Results ──────────────────────────────────────────────────────
    if "result" not in st.session_state:
        return

    st.divider()
    st.markdown("## 📊 AI Extraction Results")
    st.caption(f"Source: {st.session_state.get('source', '—')}")

    # Parse JSON
    try:
        raw_text = st.session_state["result"]
        if raw_text.strip().startswith("```"):
            raw_text = raw_text.strip().lstrip("`").lstrip("json").strip().rstrip("`").strip()
        result = json.loads(raw_text)
    except json.JSONDecodeError:
        st.error("Could not parse AI response. Raw output shown below.")
        st.code(st.session_state["result"])
        return

    run_id     = st.session_state.get("run_id", 1)
    pm_count   = result.get("pm_count", 0)
    confidence = result.get("ai_confidence", "—")
    doc_type   = result.get("document_type", "—")

    # Summary banner
    m1, m2, m3 = st.columns(3)
    m1.metric("Document Type",  doc_type)
    m2.metric("AI Confidence",  f"{confidence_colour(confidence)} {confidence}")
    m3.metric("PMs Found",      pm_count)

    if result.get("confidence_reason"):
        st.info(f"ℹ️ {result['confidence_reason']}")

    agencies = result.get("compliance_agencies_detected", [])
    if agencies:
        st.warning(
            f"⚖️ **Compliance references detected:** {', '.join(agencies)}  \n"
            "Compliance Agency field not yet available in MMM (pending TRIN-69)."
        )

    # ── Zero PM scenario ─────────────────────────────────────────────
    if pm_count == 0:
        st.error("### ❌ No PM Schedule Could Be Generated")
        reason = result.get(
            "no_pm_reason",
            "This document does not contain schedulable maintenance activities."
        )
        st.markdown(f"**Reason:** {reason}")

        with st.expander("💡 What to do next"):
            st.markdown("""
**This document describes reactive/breakdown maintenance — not a scheduled PM.**

To generate a PM schedule, try uploading one of these instead:
- An **OEM equipment manual** (e.g., Trane, Carrier, Caterpillar service manual)
- A **preventive maintenance schedule** document
- A **maintenance SOP** that includes scheduled task frequencies

Or switch to the **Voice / Text Input** tab and describe:
- *What* maintenance tasks need to be done
- *How often* they should happen (monthly, quarterly, annually)
            """)
        with st.expander("🔍 View raw AI response"):
            st.json(result)
        return

    # ── How-to hint ───────────────────────────────────────────────────
    st.markdown(
        "> 📝 **Review each PM form below.** All fields are pre-filled by AI — "
        "you can edit any value before clicking **Create PM**.  \n"
        "> Grey caption under each field shows the original AI suggestion."
    )

    # ── PM forms ─────────────────────────────────────────────────────
    freq_gap  = result.get("frequency_gap", False)
    freq_note = result.get("frequency_gap_note", "")

    for i, pm in enumerate(result.get("pms", []), start=1):
        render_pm_form(pm, freq_gap, freq_note, i, run_id)
        st.markdown("")   # spacing

    # ── Creation summary ─────────────────────────────────────────────
    created_count  = sum(
        1 for pm in result.get("pms", [])
        if st.session_state.get(f"run{run_id}_pm{pm.get('pm_number', i)}_status") == "created"
        for i in [pm.get("pm_number", 1)]
    )
    discarded_count = sum(
        1 for pm in result.get("pms", [])
        if st.session_state.get(f"run{run_id}_pm{pm.get('pm_number', i)}_status") == "discarded"
        for i in [pm.get("pm_number", 1)]
    )
    pending_count  = pm_count - created_count - discarded_count

    if created_count + discarded_count > 0:
        st.divider()
        st.markdown("### 📊 Review Summary")
        sc1, sc2, sc3 = st.columns(3)
        sc1.metric("✅ Created",  created_count)
        sc2.metric("🗑️ Discarded", discarded_count)
        sc3.metric("🟡 Pending",   pending_count)

    # ── Export ───────────────────────────────────────────────────────
    st.divider()
    st.markdown("### ⬇️ Export Results")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    ex1, ex2  = st.columns(2)

    with ex1:
        st.download_button(
            label="⬇️ Download as JSON",
            data=json.dumps(result, indent=2),
            file_name=f"pm_schedule_{timestamp}.json",
            mime="application/json",
            use_container_width=True,
        )

    with ex2:
        lines = []
        for pm in result.get("pms", []):
            lines.append(f"PM #{pm.get('pm_number')} — {pm.get('title')}")
            lines.append(f"  Category     : {pm.get('category','')}")
            lines.append(f"  Repeats      : {pm.get('repeats','')}")
            lines.append(f"  Start On     : {pm.get('start_on','')}")
            lines.append(f"  End After    : {pm.get('end_after','Blank')}")
            lines.append(f"  Assign To    : {pm.get('assign_to','Blank')}")
            lines.append(f"  Attachment   : {pm.get('add_attachment','')}")
            lines.append(f"\nDescription:\n{pm.get('description','')}")
            lines.append("\n" + "─" * 60 + "\n")

        st.download_button(
            label="⬇️ Download as Text",
            data="\n".join(lines),
            file_name=f"pm_schedule_{timestamp}.txt",
            mime="text/plain",
            use_container_width=True,
        )

    with st.expander("🔍 View raw AI response (JSON)"):
        st.json(result)


if __name__ == "__main__":
    main()
