"""`research_index._safe` must keep exactly the old guarantee after the string-walk rewrite.

The reference below is the pathlib implementation that shipped until 2026-10-21. Every case must
give the same returned path, or the same exception type and message, as the reference.
"""
import os
import stat
from pathlib import Path

import pytest

import shared_wong_choi.research_index as module
from shared_wong_choi.research_index import ResearchIndexError, _safe


def _reference_safe(path):
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts:
        raise ResearchIndexError("absolute non-symlink evidence path required")
    for item in (path, *path.parents):
        try:
            linked = stat.S_ISLNK(os.lstat(item).st_mode)
        except (OSError, ValueError):
            linked = item.is_symlink()
        if linked:
            raise ResearchIndexError("absolute non-symlink evidence path required")
    return path


def _outcome(fn, value):
    try:
        return ("ok", fn(value))
    except Exception as exc:  # noqa: BLE001 - comparing exact failure shape
        return ("raise", type(exc), str(exc))


@pytest.fixture
def tree(tmp_path):
    root = tmp_path.resolve()
    (root / "real" / "deep" / "er").mkdir(parents=True)
    (root / "real" / "deep" / "er" / "record.json").write_text("{}")
    (root / "leaf-link.json").symlink_to(root / "real" / "deep" / "er" / "record.json")
    (root / "mid-link").symlink_to(root / "real" / "deep", target_is_directory=True)
    (root / "dangling").symlink_to(root / "nowhere")
    return root


def _cases(root):
    r = str(root)
    return [
        root / "real" / "deep" / "er" / "record.json",            # plain file
        root / "real" / "deep" / "er",                              # plain directory
        root / "real" / "absent.json",                              # missing leaf
        root / "absent" / "also-absent" / "x.json",                 # missing middle
        root / "real" / "deep" / "er" / "record.json" / "child",    # file used as directory
        root / "leaf-link.json",                                    # symlink at leaf
        root / "mid-link" / "er" / "record.json",                   # symlink in the middle
        root / "dangling",                                          # dangling symlink
        root / "dangling" / "child",                                # below a dangling symlink
        f"{r}/real//deep/./er/record.json",                         # // and . normalised by Path
        f"{r}/real/deep/er/",                                       # trailing slash
        f"{r}/real/../real/deep",                                   # ..
        "relative/record.json",                                     # relative
        "/",                                                        # root
        f"{r}/real/bad\0name",                                      # NUL → ValueError path
        Path(r) / "real",                                           # Path input
        f"/{r}/real",                                               # POSIX "//" prefix (pathlib keeps it)
        "//",                                                       # bare "//"
    ]


def test_matches_reference_on_every_edge_case(tree):
    for value in _cases(tree):
        assert _outcome(_safe, value) == _outcome(_reference_safe, value), value


def test_symlinked_ancestor_above_the_tree_is_rejected(tmp_path):
    root = tmp_path.resolve()
    (root / "top").mkdir()
    (root / "top" / "x.json").write_text("{}")
    (root / "alias").symlink_to(root / "top", target_is_directory=True)
    with pytest.raises(ResearchIndexError, match="non-symlink"):
        _safe(root / "alias" / "x.json")


def test_every_ancestor_is_checked_once_per_call(tree, monkeypatch):
    seen = []
    real = module.os.lstat

    def counting(item, *args, **kwargs):
        seen.append(os.fspath(item))
        return real(item, *args, **kwargs)

    monkeypatch.setattr(module.os, "lstat", counting)
    path = tree / "real" / "deep" / "er" / "record.json"
    assert _safe(path) == path
    expected = [str(path), *map(str, path.parents)]
    assert seen == expected
    seen.clear()
    _safe(path)                     # no caching: a second call checks every level again
    assert seen == expected


def test_change_between_calls_is_seen(tree):
    path = tree / "real" / "deep" / "er" / "record.json"
    assert _safe(path) == path
    moved = tree / "real" / "deep-moved"
    (tree / "real" / "deep").rename(moved)
    (tree / "real" / "deep").symlink_to(moved, target_is_directory=True)
    with pytest.raises(ResearchIndexError, match="non-symlink"):
        _safe(path)


def test_artifact_path_through_symlinked_directory_is_still_rejected_at_read(tmp_path):
    """`_attempt` no longer re-checks; the check right before the O_NOFOLLOW open must still fire."""
    import hashlib
    from shared_wong_choi.evidence import ArtifactRef
    from shared_wong_choi.research_prediction_artifacts import _attempt, _Blobs
    root = tmp_path.resolve()
    (root / "real").mkdir()
    (root / "real" / "a.json").write_bytes(b"{}")
    (root / "alias").symlink_to(root / "real", target_is_directory=True)
    linked = root / "alias" / "a.json"
    ref = ArtifactRef(path=str(linked), sha256=hashlib.sha256(b"{}").hexdigest(),
                      captured_at="2026-10-21T00:00:00+00:00", source="test")
    with pytest.raises(ResearchIndexError, match="non-symlink"):
        _attempt((ref,), (linked,), "direct", _Blobs(lambda: None))
    with pytest.raises(ResearchIndexError, match="non-symlink"):
        _Blobs(lambda: None).read(linked)
