"""Decode self-contained AU report metadata without importing today's engine."""
import base64
import hashlib
import json
import math
import re

MARKER = 'wc-au-dimensions:'
BLOCK = re.compile(r'<!-- wc-au-dimensions:v1:([A-Za-z0-9+/=]+) -->')


def read_registry_metadata(text):
    """Absent legacy metadata is unknown; malformed metadata is an error."""
    matches = list(BLOCK.finditer(text))
    if MARKER not in text:
        return None, text
    if len(matches) != 1 or text.count(MARKER) != 1:
        raise ValueError('AU dimension metadata malformed or ambiguous')
    token = matches[0].group(1)
    if len(token) > 65536:
        raise ValueError('AU dimension metadata too large')
    try:
        value = json.loads(base64.b64decode(token, validate=True).decode('utf-8'))
        if not isinstance(value, dict) or value.get('schema') != 'au/dimensions-v1':
            raise ValueError('AU dimension schema unsupported')
        digest = value['registry_sha256']
        payload = {k: v for k, v in value.items() if k != 'registry_sha256'}
        canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'),
                               ensure_ascii=True, allow_nan=False).encode()
        if hashlib.sha256(canonical).hexdigest() != digest:
            raise ValueError('AU dimension metadata hash mismatch')
        leaves, dimensions = value['leaves'], value['dimensions']
        if not isinstance(leaves, list) or not isinstance(dimensions, list):
            raise ValueError('AU dimension spec lists missing')
        leaf_keys = [x['key'] for x in leaves]
        dim_keys = [x['key'] for x in dimensions]
        if (len(set(leaf_keys)) != len(leaf_keys) or len(set(dim_keys)) != len(dim_keys)
                or any(not isinstance(k, str) or not k for k in leaf_keys + dim_keys)):
            raise ValueError('AU dimension keys invalid or duplicated')
        for spec in dimensions:
            if not isinstance(spec['label'], str) or not spec['label']:
                raise ValueError('AU dimension label invalid')
            coefficient = spec['coefficient']
            if coefficient is not None and (isinstance(coefficient, bool)
                    or not isinstance(coefficient, (float, int)) or not math.isfinite(coefficient)):
                raise ValueError('AU dimension coefficient invalid')
            for key, weight in spec['leaves']:
                if key not in leaf_keys or isinstance(weight, bool) or not isinstance(weight, (float, int)) or not math.isfinite(weight):
                    raise ValueError('AU dimension leaf binding invalid')
    except (KeyError, TypeError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError('AU dimension metadata invalid') from exc
    return value, text[:matches[0].start()] + text[matches[0].end():]
