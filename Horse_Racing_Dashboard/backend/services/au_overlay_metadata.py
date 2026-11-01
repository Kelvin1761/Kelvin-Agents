"""Read the captured AU score overlays (綜合分 = 七維 + overlay); never recompute them in the UI."""

import base64
import json
import re

MARKER = "<!-- wc-au-overlays:"
BLOCK = re.compile(r"<!-- wc-au-overlays:v1:([A-Za-z0-9+/=]+) -->")


def reject_constant(value):
    raise ValueError("non-finite AU overlay metadata")


def read_overlay_metadata(text):
    if MARKER not in text:
        return None, text
    matches = list(BLOCK.finditer(text))
    if len(matches) != 1 or text.count(MARKER) != 1 or len(matches[0][1]) > 262144:
        raise ValueError("AU overlay metadata malformed or ambiguous")
    value = json.loads(base64.b64decode(matches[0][1], validate=True), parse_constant=reject_constant)
    if not isinstance(value, dict) or value.get("schema") != "au/overlays-v1" or not isinstance(value.get("horses"), dict):
        raise ValueError("AU overlay metadata schema unsupported")
    return value, text.replace(matches[0][0], "")
