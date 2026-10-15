"""Read captured AU full-time evidence; never reconstruct a prediction in UI."""

import base64
import json
import re

MARKER = "<!-- wc-au-full-time:"
BLOCK = re.compile(r"<!-- wc-au-full-time:v1:([A-Za-z0-9+/=]+) -->")


def reject_constant(value):
    raise ValueError("non-finite AU full-time metadata")


def read_time_metadata(text):
    if MARKER not in text:
        return None, text
    matches = list(BLOCK.finditer(text))
    if len(matches) != 1 or text.count(MARKER) != 1 or len(matches[0][1]) > 262144:
        raise ValueError("AU full-time metadata malformed or ambiguous")
    value = json.loads(base64.b64decode(matches[0][1], validate=True), parse_constant=reject_constant)
    if (
        not isinstance(value, dict)
        or value.get("schema") != "au/full-time-v1"
        or not isinstance(value.get("horses"), dict)
    ):
        raise ValueError("AU full-time metadata schema unsupported")
    audit = value.get("race")
    if audit is not None and (not isinstance(audit, dict) or audit.get("model_version") != "AU_CONTEXT_TOTAL_V1"):
        raise ValueError("AU full-time metadata model unsupported")
    return value, text.replace(matches[0][0], "")
