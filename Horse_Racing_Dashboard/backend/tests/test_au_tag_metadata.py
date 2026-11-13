import base64
import json

import pytest

from services.au_tag_metadata import read_tag_metadata


def _block(payload):
    return f"<!-- wc-au-tags:v1:{base64.b64encode(json.dumps(payload).encode()).decode()} -->"


def test_roundtrip_and_strip():
    payload = {"schema": "au/tags-v1", "horses": {"3": {"name": "Swing State", "tags": {"good": [{"label": "首本路程"}], "bad": [], "note": []}}}}
    value, text = read_tag_metadata("x\n" + _block(payload) + "\ny")
    assert value["horses"]["3"]["tags"]["good"][0]["label"] == "首本路程"
    assert "wc-au-tags" not in text


def test_absent_is_none():
    assert read_tag_metadata("plain")[0] is None


def test_wrong_schema_rejected():
    with pytest.raises(ValueError):
        read_tag_metadata(_block({"schema": "x", "horses": {}}))
