"""Read the AU per-horse tags (engine `au_racing_engine/tags.py`, display only)."""

import base64
import json
import re

MARKER = "<!-- wc-au-tags:"
BLOCK = re.compile(r"<!-- wc-au-tags:v1:([A-Za-z0-9+/=]+) -->")


def _reject_constant(value):
    raise ValueError("non-finite AU tag metadata")


def read_tag_metadata(text):
    if MARKER not in text:
        return None, text
    matches = list(BLOCK.finditer(text))
    if len(matches) != 1 or text.count(MARKER) != 1 or len(matches[0][1]) > 524288:
        raise ValueError("AU tag metadata malformed or ambiguous")
    value = json.loads(base64.b64decode(matches[0][1], validate=True), parse_constant=_reject_constant)
    if not isinstance(value, dict) or value.get("schema") != "au/tags-v1" or not isinstance(value.get("horses"), dict):
        raise ValueError("AU tag metadata schema unsupported")
    return value, text.replace(matches[0][0], "")
