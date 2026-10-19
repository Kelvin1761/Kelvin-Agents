"""Phase-local native graph reuse, never a persisted or caller-supplied proof.

Every reuse rechecks the complete original source bytes and directory listings.
This caches validated metadata structure only, not blobs, labels or authority.
Operational use still requires the supervisor's resource checkpoint.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Callable

from .contracts import Domain
from .evidence import RecordKind
from .research_index import _MetadataPages, _at, _encoded, _hashed, _safe


class _NativeEvidenceSnapshot:
    __slots__ = ("_root", "_domain", "_end", "_records", "_files", "_directories", "_inventory_witnesses")

    def __init__(self, *, root: Path, domain: Domain, as_of: datetime,
                 checkpoint: Callable[[], None] = lambda: None):
        checkpoint()
        if not isinstance(domain, Domain) or domain not in (Domain.AU, Domain.HKJC):
            raise ValueError("native racing snapshot scope required")
        root, end = _safe(Path(root)), _at(as_of)
        if not root.is_dir() or not (root / "records").is_dir():
            raise ValueError("native evidence source unavailable")
        if domain is Domain.AU:
            from .research_au_settlement_source import _evidence
        else:
            from .research_hkjc_settlement_source import _evidence
        reader = _MetadataPages(checkpoint)
        records = _evidence(root, end, reader)
        reader.recheck()
        self._root, self._domain, self._end = root, domain, end
        self._files = tuple(sorted(reader.files.items()))
        self._directories = tuple(sorted(reader.directories.items()))
        self._records = deepcopy(records)
        self._inventory_witnesses = None

    def verify_inventories(self, prediction: dict, settlement: dict, *, root: Path,
                           domain: Domain, as_of: datetime,
                           checkpoint: Callable[[], None] = lambda: None) -> None:
        """Bind both canonical inventories to one complete source read/recheck."""
        from .research_prediction_pages import SCHEMA as prediction_schema, MAX_INVENTORY_BYTES, freeze_prediction_inventory
        from .research_racing_settlement_inventory import SCHEMA as settlement_schema, freeze_racing_settlement_inventory
        supplied = (prediction, settlement)
        for value, schema in zip(supplied, (prediction_schema, settlement_schema)):
            _hashed(value, schema)
            if len(_encoded(value)) > MAX_INVENTORY_BYTES:
                raise ValueError("oversized combined inventory")
        reader = self._source_reader(root=root, domain=domain, as_of=as_of, checkpoint=checkpoint)
        expected = self._inventory_witnesses
        if expected is None:
            options = dict(root=self._root, domain=self._domain, as_of=self._end, checkpoint=checkpoint)
            expected = (_encoded(freeze_prediction_inventory(**options)),
                        _encoded(freeze_racing_settlement_inventory(**options)))
        if tuple(_encoded(value) for value in supplied) != expected:
            raise ValueError("combined inventory differs from complete canonical source")
        reader.recheck()
        checkpoint()
        if tuple(_encoded(value) for value in supplied) != expected:
            raise ValueError("combined inventory changed during verification")
        # Only canonical source-built witnesses are retained, never caller data.
        self._inventory_witnesses = expected

    def read(self, *, root: Path, domain: Domain, as_of: datetime,
             checkpoint: Callable[[], None] = lambda: None) -> dict:
        records, reader = self._begin_read(root=root, domain=domain, as_of=as_of, checkpoint=checkpoint)
        reader.recheck()
        checkpoint()
        return records

    def _begin_read(self, *, root: Path, domain: Domain, as_of: datetime,
                    checkpoint: Callable[[], None], selected_prediction_ids=None) -> tuple[dict, _MetadataPages]:
        """Native caller must recheck this reader after its blob/label work."""
        reader = self._source_reader(root=root, domain=domain, as_of=as_of, checkpoint=checkpoint)
        records = self._records
        if selected_prediction_ids is not None:
            def record(value):
                return value[0] if self._domain is Domain.AU else value

            selected = {key for key in selected_prediction_ids if key in records
                        and record(records[key]).kind is RecordKind.PREDICTION}
            decisions = {key for key, value in records.items()
                         if record(value).kind is RecordKind.DECISION
                         and record(value).links["prediction_id"] in selected}
            settlements = {key for key, value in records.items()
                           if record(value).kind is RecordKind.SETTLEMENT
                           and record(value).links["decision_id"] in decisions}
            parents = {record(records[key]).links["model_release_id"] for key in selected}
            selected |= decisions | settlements | parents
            records = {key: value for key, value in records.items() if key in selected}
        return deepcopy(records), reader

    @property
    def record_count(self) -> int:
        """Full validated graph count, independent of a detached page projection."""
        return len(self._records)

    def _source_reader(self, *, root: Path, domain: Domain, as_of: datetime,
                       checkpoint: Callable[[], None]) -> _MetadataPages:
        checkpoint()
        if (not isinstance(domain, Domain)
                or (_safe(Path(root)), domain, _at(as_of)) != (self._root, self._domain, self._end)):
            raise ValueError("native evidence snapshot scope mismatch")
        # Every metadata page preserves native byte bounds; graph count is global.
        # No mtime-only cache or resource-check throttling is used.
        reader = _MetadataPages(checkpoint)
        for folder, expected in self._directories:
            if tuple(path.name for path in reader.listing(folder)) != expected:
                raise ValueError("native evidence snapshot directory changed")
        for path, expected in self._files:
            _, digest = reader.read(path)
            if digest != expected:
                raise ValueError("native evidence snapshot bytes changed")
        return reader
