"""Parser for synthetic HL7 v2 application ACKs in DocuRecon v0.1.

MSA-1 provides the application acknowledgement and MSA-2 references the
outbound MSH-10 control ID. AA/AE/AR are *application* acknowledgements;
none establishes successful downstream regulatory reporting.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path
import re

CODES = {'AA': 'ACCEPTED', 'AE': 'APPLICATION_ERROR', 'AR': 'APPLICATION_REJECTED'}


def parse_ack_text(raw: str, source: str = '<memory>') -> dict:
    segments = {}
    for segment in re.split(r'[\r\n]+', raw.lstrip('\ufeff')):
        if not segment.strip():
            continue
        parts = segment.strip().split('|')
        if parts[0] in ('MSH', 'MSA'):
            if parts[0] in segments:
                raise ValueError(f'Duplicate {parts[0]} segment')
            segments[parts[0]] = parts
        elif parts[0] == 'ERR':
            segments.setdefault('ERR', []).append(parts)
    if 'MSH' not in segments or 'MSA' not in segments:
        raise ValueError('ACK must include both MSH and MSA segments')
    msh, msa = segments['MSH'], segments['MSA']
    # MSH-9 and MSH-10 are at split indices 8 and 9, unlike other segments.
    def at(parts, index):
        return parts[index].strip() if len(parts) > index else ''
    msg_type = at(msh, 8)
    if not (msg_type == 'ACK' or msg_type.startswith('ACK^')):
        raise ValueError(f'Expected ACK message type in MSH-9, got {msg_type!r}')
    ack_id = at(msh, 9)
    if not ack_id:
        raise ValueError('Missing MSH-10 acknowledgement message ID')
    code = at(msa, 1)
    outbound_id = at(msa, 2)
    if code not in CODES:
        raise ValueError(f'Unsupported application acknowledgement MSA-1: {code or "missing"}')
    if not outbound_id:
        raise ValueError('Missing MSA-2 referenced outbound control ID')
    timestamp = at(msh, 6)
    try:
        received_at = datetime.strptime(timestamp, '%Y%m%d%H%M%S').isoformat(timespec='seconds')
    except ValueError as exc:
        raise ValueError('MSH-7 timestamp must be YYYYMMDDHHMMSS') from exc
    notes = at(msa, 3)
    err_details = ['|'.join(p[1:]) for p in segments.get('ERR', [])]
    return {'source': source, 'ack_message_id': ack_id, 'control_id': outbound_id,
            'ack_code': code, 'ack_class': CODES[code], 'received_at': received_at,
            'ack_text': notes, 'error_details': '; '.join(err_details),
            'parse_status': 'PARSED_SYNTHETIC_ACK'}


def parse_ack_file(path: Path) -> dict:
    path = Path(path)
    return parse_ack_text(path.read_text(encoding='utf-8-sig'), source=path.name)


def parse_ack_folder(folder: Path) -> tuple[list[dict], list[dict]]:
    folder = Path(folder)
    rows, errors = [], []
    if not folder.exists():
        return rows, errors
    for path in sorted(folder.iterdir()):
        if path.is_file() and path.suffix.lower() in ('.hl7', '.ack', '.txt'):
            try:
                rows.append(parse_ack_file(path))
            except Exception as exc:
                errors.append({'source': path.name, 'error': str(exc)})
    return rows, errors


def link_acknowledgements(messages: list[dict], acks: list[dict]) -> list[dict]:
    """Link ACKs to outbound control IDs; unmatched/duplicate ACKs stay visible.

    No claims of a true 'missing ACK' until the expected window, delivery
    channel, and retrieval completeness have been specified.
    """
    outbound_counts = Counter(m['control_id'] for m in messages)
    ack_counts = Counter(a['control_id'] for a in acks)
    linked = []
    for m in messages:
        control = m['control_id']
        found = [a for a in acks if a['control_id'] == control]
        if outbound_counts[control] > 1:
            status = 'DUPLICATE_OUTBOUND_CONTROL_ID'
        elif len(found) > 1:
            status = 'MULTIPLE_ACKS_FOR_CONTROL_ID'
        elif not found:
            status = 'NO_ACK_IN_SAMPLE'  # Not a confirmed missing ACK
        else:
            status = found[0]['ack_class']
        linked.append({'outbound_control_id': control, 'outbound_file': m['source'],
                       'ack_file': ', '.join(a['source'] for a in found),
                       'ack_code': ', '.join(a['ack_code'] for a in found),
                       'link_status': status})
    for a in acks:
        if a['control_id'] not in outbound_counts:
            linked.append({'outbound_control_id': a['control_id'], 'outbound_file': '',
                           'ack_file': a['source'], 'ack_code': a['ack_code'],
                           'link_status': 'ORPHAN_ACK_NO_OUTBOUND_MESSAGE'})
    return linked
