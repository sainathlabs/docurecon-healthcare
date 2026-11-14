"""Small, explicit HL7 v2 ADT parser for DocuRecon's *synthetic* v0.1 profile.

This does not cover real facility interfaces or full HL7 escaping/repetitions.
Custom ZLS fields are DocuRecon-specific and NOT standard NICS mapping.
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime
import re


def parse_hl7_text(raw: str, source: str = '<memory>') -> dict:
    segments = [s.strip() for s in re.split(r'[\r\n]+', raw.lstrip('\ufeff')) if s.strip()]
    parsed = {}
    for segment in segments:
        cells = segment.split('|')
        kind = cells[0]
        if kind in parsed:
            raise ValueError(f'Duplicate {kind} segment is not supported in v0.1')
        parsed[kind] = cells
    for required in ('MSH', 'PID', 'PV1', 'ZLS'):
        if required not in parsed:
            raise ValueError(f'Missing {required} segment')

    def item(kind, number):
        # For MSH, the explicit field separator is MSH-1 and splitting shifts numbering by one.
        index = number - 1 if kind == 'MSH' else number
        row = parsed[kind]
        return row[index].strip() if index < len(row) else ''

    msg_type = item('MSH', 9)
    control = item('MSH', 10)
    if not msg_type.startswith('ADT^'):
        raise ValueError(f'Expected ADT event, got {msg_type or "missing MSH-9"}')
    if not control:
        raise ValueError('Missing MSH-10 message control ID')
    patient_id = item('PID', 3).split('^')[0]
    encounter_id = item('PV1', 19).split('^')[0]
    if not patient_id or not encounter_id:
        raise ValueError('Missing PID-3 patient ID or PV1-19 encounter ID')
    timestamp = item('MSH', 7)
    try:
        transmitted_at = datetime.strptime(timestamp[:14], '%Y%m%d%H%M%S').isoformat(timespec='seconds')
    except ValueError as exc:
        raise ValueError(f'Invalid MSH-7 timestamp: {timestamp}') from exc
    status = item('ZLS', 1)
    date = item('ZLS', 2)
    time = item('ZLS', 3)
    if status not in ('9.39', '9.37'):
        raise ValueError('ZLS-1 must be 9.39 or 9.37 in the synthetic profile')
    try:
        completion = datetime.strptime(date + time, '%Y%m%d%H%M').isoformat(timespec='minutes')
    except ValueError as exc:
        raise ValueError('ZLS-2 and ZLS-3 must be YYYYMMDD and HHMM') from exc
    return {'source': source, 'message_type': msg_type, 'control_id': control,
            'patient_id': patient_id, 'encounter_id': encounter_id,
            'patient_name': item('PID', 5), 'legal_status': status,
            'completion_timestamp': completion, 'transmitted_at': transmitted_at,
            'parse_status': 'PARSED_SYNTHETIC_PROFILE'}


def parse_hl7_file(path: Path) -> dict:
    return parse_hl7_text(Path(path).read_text(encoding='utf-8-sig'), source=Path(path).name)


def parse_hl7_folder(folder: Path) -> tuple[list[dict], list[dict]]:
    rows, errors = [], []
    for path in sorted(Path(folder).glob('*')) if Path(folder).exists() else []:
        if path.is_file() and path.suffix.lower() in ('.hl7', '.txt'):
            try:
                rows.append(parse_hl7_file(path))
            except Exception as exc:
                errors.append({'source': path.name, 'error': str(exc)})
    return rows, errors
