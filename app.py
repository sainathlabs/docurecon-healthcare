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
            )

        st.session_state["daily_date"] = selected.isoformat()
    except Exception as exc:
        st.error(f'Reconciliation could not complete: {exc}')

if 'daily_result' in st.session_state:
    result = st.session_state['daily_result']
    st.divider()
    st.subheader('Daily reconciliation results · ' + result['date'])
    measures = [('Paperwork for date', 'paperwork_count'), ('HL7 messages supplied', 'hl7_count'),
                ('ACK files supplied', 'ack_count'), ('Provisional matches', 'provisional_matches'),
                ('Provisional exceptions', 'provisional_exceptions'), ('OCR uncertain', 'ocr_uncertain')]
    for col, (label, key) in zip(st.columns(6), measures):
        col.metric(label, result[key])
    st.warning(result['note'])
    records = pd.DataFrame(result['rows'])
    if not records.empty:
        st.subheader('Exception and uncertainty list')
        exceptions = records[records['status'] != 'PROVISIONAL_MATCH']
        if exceptions.empty: st.success('No provisional exceptions in the selected records.')
        else: st.dataframe(exceptions, use_container_width=True, hide_index=True)
        with st.expander('All paperwork comparisons', expanded=True):
            st.dataframe(records, use_container_width=True, hide_index=True)
        st.download_button('Download reconciliation CSV', records.to_csv(index=False).encode('utf-8'),
                           f'docurecon_daily_{result["date"]}.csv', 'text/csv')
    else:
        st.info('No paperwork completion dates could be associated with this day. Check your inputs and scan quality.')
    if result['parse_errors']:
        st.error(f'{len(result["parse_errors"])} input file(s) could not be parsed.')
        st.dataframe(pd.DataFrame(result['parse_errors']), use_container_width=True, hide_index=True)
    if result['orphan_acks']:
        st.warning('Acknowledgements referencing an outbound control ID absent from the supplied HL7 files:')
        st.dataframe(pd.DataFrame(result['orphan_acks']), use_container_width=True, hide_index=True)

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
