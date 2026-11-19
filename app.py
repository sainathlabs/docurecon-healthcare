"""DocuRecon: local synthetic-data-first daily reconciliation dashboard."""
from datetime import date
from pathlib import Path
import sys
import streamlit as st
import pandas as pd

PROJECT = Path(__file__).resolve().parent

sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT / "src"))
from docurecon.reconciliation.daily_engine import run_daily

st.set_page_config(page_title='DocuRecon | Daily Reconciliation', layout='wide')
st.title('DocuRecon')
st.caption('Healthcare Documentation and HL7 Reconciliation Framework · Local synthetic research prototype')
st.info('Select the date on which the involuntary paperwork was completed. Place files in the three folders below or upload them, then click Run Daily Reconciliation.')
selected = st.date_input('Paperwork completion date', date(2026, 11, 12), format='YYYY-MM-DD')
base = Path(st.text_input('Input folder location', str(PROJECT / 'sample_data'))).expanduser()
cols = st.columns(3)
folders = [('paperwork', '1. Involuntary paperwork', ['pdf']),
           ('hl7', '2. HL7 outbound messages', ['hl7','txt']),
           ('acknowledgements', '3. HL7 ACK / NACK', ['ack','hl7','txt'])]
uploads = {}
for col, (folder, title, allowed) in zip(cols, folders):
    with col:
        st.subheader(title)
        st.code(str(base / folder), language=None)
        uploads[folder] = st.file_uploader('Select files (optional)', type=allowed,
                                            accept_multiple_files=True, key='upload_' + folder)
        count = len([p for p in (base / folder).iterdir() if p.is_file() and p.suffix.lower().lstrip('.') in allowed]) if (base / folder).is_dir() else 0
        st.caption(f'{count} local file(s) detected')

use_ai = st.checkbox(
    "Enable AI-assisted validation (synthetic documents only)",
    value=False,
    help=(
        "Uses the OpenAI API on selected synthetic PDFs. "
        "Requires API access and may incur charges."
    ),
)


# Optional AI review of documents excluded by OCR date selection.
# Disabled by default to avoid unexpected API requests.
review_excluded_dates = st.checkbox(
    "Review OCR-excluded document dates using AI",
    value=False,
    help=(
        "Examines a limited number of excluded synthetic PDFs "
        "for possible date-assignment errors. "
        "Uses the OpenAI API and may incur charges. "
        "Does not automatically change daily reconciliation."
    ),
)

max_date_review_calls = 0

if review_excluded_dates:
    max_date_review_calls = st.number_input(
        "Maximum additional AI date-review requests",
        min_value=1,
        max_value=30,
        value=3,
        step=1,
        help=(
            "Maximum number of excluded PDFs attempted "
            "during this reconciliation run. "
            "Separate from AI validation of selected paperwork."
        ),
    )

st.caption(
    "AI date review is restricted to approved synthetic "
    "development documents. All results remain provisional."
)


if st.button(
    "Run Daily Reconciliation",
    type="primary",
    use_container_width=True,
):
    st.session_state.pop("daily_result", None)
    try:
        for folder, files in uploads.items():
            destination = base / folder
            destination.mkdir(parents=True, exist_ok=True)
            for f in files:
                safe_name = Path(f.name).name
                if safe_name not in ('', '.', '..'):
                    target = destination / safe_name
                    if target.exists():
                        raise FileExistsError(
                            f"File already exists: {target.name}. "
                            "Rename the uploaded file or remove the existing copy."
                        )

                    target.write_bytes(f.getvalue())
        with st.spinner(
            "Extracting paperwork, parsing HL7 and ACKs, "
            "and comparing records..."
        ):
            st.session_state["daily_result"] = run_daily(
                base,
                selected,
                use_ai=use_ai,
                review_excluded_dates_with_ai=review_excluded_dates,
                max_date_review_ai_calls=int(max_date_review_calls),
            )

        st.session_state["daily_date"] = selected.isoformat()
    except Exception as exc:
        st.error(f'Reconciliation could not complete: {exc}')


if "daily_result" in st.session_state:
    result = st.session_state["daily_result"]
    report_date = result["date"]

    st.divider()
    st.subheader(f"Daily reconciliation results: {report_date}")

    # --------------------------------------------------
    # Summary metrics
    # --------------------------------------------------
    measures = [
        ("Paperwork for date", result["paperwork_count"]),
        ("HL7 supplied", result["hl7_count"]),
        ("ACK supplied", result["ack_count"]),
        ("Provisional matches", result["provisional_matches"]),
        ("Provisional exceptions", result["provisional_exceptions"]),
        ("All OCR uncertain", result["ocr_uncertain"]),
    ]

    for col, (label, value) in zip(st.columns(6), measures):
        col.metric(label, value)

    st.caption(
        "All OCR uncertain includes unassigned paperwork "
        "from the supplied folder, not only selected-day records."
    )
    st.warning(result["note"])

    # --------------------------------------------------
    # Section 1: Daily reconciliation
    # --------------------------------------------------
    st.subheader("1. Daily reconciliation")

    daily = pd.DataFrame(result.get("daily_rows", []))

    if daily.empty:
        st.info(
            "No paperwork was assigned to this reporting "
            "date by the existing OCR selection process."
        )
    else:
        exceptions = daily[
            daily["status"] != "PROVISIONAL_MATCH"
        ]

        if exceptions.empty:
            st.info(
                "No provisional exceptions among "
                "the selected-day records."
            )
        else:
            st.markdown("**Exceptions and uncertainty**")
            st.dataframe(
                exceptions,
                use_container_width=True,
                hide_index=True,
            )

        with st.expander(
            "All selected-day comparisons",
            expanded=True,
        ):
            st.dataframe(
                daily,
                use_container_width=True,
                hide_index=True,
            )

        st.download_button(
            "Download daily reconciliation CSV",
            daily.to_csv(index=False).encode("utf-8"),
            file_name=f"docurecon_daily_{report_date}.csv",
            mime="text/csv",
            key="download_daily",
        )


    # --------------------------------------------------
    # Patient identity evidence review
    # --------------------------------------------------
    st.subheader("Patient identity evidence")

    st.caption(
        "Compares OCR paperwork, AI extraction and HL7. "
        "Agreement does not verify patient identity."
    )

    identity_columns = [
        "paperwork_file",
        "patient_name",
        "ocr_mrn",
        "control_id",
        "match_method",
        "identity_name_status",
        "identity_mrn_status",
        "identity_name_ocr_vs_ai",
        "identity_name_ocr_vs_hl7",
        "identity_name_ai_vs_hl7",
        "identity_mrn_ocr_vs_ai",
        "identity_mrn_ocr_vs_hl7",
        "identity_mrn_ai_vs_hl7",
        "identity_review_required",
        "identity_verified",
    ]

    if daily.empty:
        st.info(
            "No selected-day paperwork available "
            "for identity comparison."
        )

    elif "identity_review_required" not in daily.columns:
        st.info(
            "Three-source identity comparison was not "
            "performed. Enable AI-assisted validation "
            "to evaluate OCR, AI and HL7 evidence."
        )

    else:
        # Keep a consistent table even when some
        # candidate comparisons were not evaluated.
        identity_table = daily.reindex(
            columns=identity_columns
        ).fillna("NOT_EVALUATED")

        review_mask = (
            identity_table["identity_review_required"]
            .astype(str)
            .str.lower()
            == "true"
        )

        flagged = identity_table.loc[review_mask]

        col1, col2 = st.columns(2)

        col1.metric(
            "Identity comparisons",
            len(identity_table),
        )

        col2.metric(
            "Identity review required",
            len(flagged),
        )

        if flagged.empty:
            st.info(
                "No additional identity-review flags "
                "among evaluated records. Identity "
                "is still not independently verified."
            )
        else:
            st.warning(
                "These records contain missing or "
                "conflicting identity evidence."
            )

            st.dataframe(
                flagged,
                use_container_width=True,
                hide_index=True,
            )

        with st.expander(
            "All identity evidence comparisons"
        ):
            st.dataframe(
                identity_table,
                use_container_width=True,
                hide_index=True,
            )

        st.download_button(
            "Download identity evidence CSV",
            identity_table.to_csv(
                index=False
            ).encode("utf-8"),
            file_name=(
                f"docurecon_identity_{report_date}.csv"
            ),
            mime="text/csv",
            key="download_identity",
        )


    # --------------------------------------------------
    # Section 2: Unassigned paperwork
    # --------------------------------------------------
    st.subheader("2. Unassigned paperwork")

    unassigned = pd.DataFrame(
        result.get("unassigned_paperwork", [])
    )

    if unassigned.empty:
        st.info("No paperwork with a missing OCR date.")
    else:
        st.warning(
            f"{len(unassigned)} document(s) could not be "
            "assigned to a date using OCR."
        )

        st.dataframe(
            unassigned,
            use_container_width=True,
            hide_index=True,
        )

        st.download_button(
            "Download unassigned paperwork CSV",
            unassigned.to_csv(index=False).encode("utf-8"),
            file_name=f"docurecon_unassigned_{report_date}.csv",
            mime="text/csv",
            key="download_unassigned",
        )

    # --------------------------------------------------
    # Section 3: AI date review
    # --------------------------------------------------
    st.subheader("3. Date-assignment review queue")

    date_reviews = pd.DataFrame(
        result.get("date_review_queue", [])
    )

    ai_calls = result.get("date_review_ai_calls", 0)
    ai_errors = result.get("date_review_ai_errors", [])

    col1, col2, col3 = st.columns(3)

    col1.metric("Date-review records", len(date_reviews))
    col2.metric("Additional AI attempts", ai_calls)
    col3.metric("AI review failures", len(ai_errors))

    if date_reviews.empty:
        st.info(
            "No date-assignment review entries for "
            "the supplied evidence."
        )
    else:
        st.warning(
            "These are review candidates, not verified "
            "legal completion dates or confirmed admissions."
        )

        st.dataframe(
            date_reviews,
            use_container_width=True,
            hide_index=True,
        )

        st.download_button(
            "Download date-review CSV",
            date_reviews.to_csv(index=False).encode("utf-8"),
            file_name=f"docurecon_date_review_{report_date}.csv",
            mime="text/csv",
            key="download_date_review",
        )

    if ai_errors:
        st.error(
            f"{len(ai_errors)} AI date-review attempt(s) failed."
        )
        st.dataframe(
            pd.DataFrame(ai_errors),
            use_container_width=True,
            hide_index=True,
        )

    # --------------------------------------------------
    # Parse errors and orphan acknowledgements
    # --------------------------------------------------
    if result["parse_errors"]:
        st.error(
            f'{len(result["parse_errors"])} input file(s) '
            "could not be parsed."
        )
        st.dataframe(
            pd.DataFrame(result["parse_errors"]),
            use_container_width=True,
            hide_index=True,
        )

    if result["orphan_acks"]:
        st.warning(
            "ACK messages reference control IDs absent "
            "from the supplied outbound HL7 files."
        )
        st.dataframe(
            pd.DataFrame(result["orphan_acks"]),
            use_container_width=True,
            hide_index=True,
        )

    # Preserve the original combined output for research.
    with st.expander("Legacy combined reconciliation output"):
        combined = pd.DataFrame(result["rows"])

        if not combined.empty:
            st.dataframe(
                combined,
                use_container_width=True,
                hide_index=True,
            )

with st.expander('Developer tools · inspect each input independently'):
    if st.button('Inspect source parsers'):
        from docurecon.parsers.paperwork_parser import extract_folder
        from docurecon.parsers.hl7_parser import parse_hl7_folder
        from docurecon.parsers.ack_parser import parse_ack_folder, link_acknowledgements
        papers, pe = extract_folder(base / 'paperwork')
        messages, he = parse_hl7_folder(base / 'hl7')
        acks, ae = parse_ack_folder(base / 'acknowledgements')
        for title, items in [('Paperwork OCR', papers), ('Outbound HL7',messages),
                             ('ACK/NACK',acks),('ACK links',link_acknowledgements(messages, acks))]:
            st.markdown('**' + title + '**')
            st.dataframe(pd.DataFrame(items), hide_index=True, use_container_width=True)
        if pe or he or ae:
            st.error('Some files could not be parsed')
            st.dataframe(pd.DataFrame(pe + he + ae), hide_index=True)
