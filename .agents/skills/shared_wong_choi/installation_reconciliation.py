"""Forward installer eligibility and append-only requests for fresh gates.

The preview is read-only. Intent creation records a pending request that still
requires a fresh full gate and independent approval before installation.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping
from urllib.parse import quote

from .release_activation import EXPECTED_MUTABLE_PATHS, _is_ancestor
from .release_approval import _load_release
from .release_events import EVENT_SCHEMA, EVENT_TYPES, _hash, effective_status
from .release_manager import ReleaseError, _run

INSTALLER = ".agents/skills/central_wong_choi/install_production_runtime.sh"
DOMAINS = ("au", "hkjc", "nba", "tennis")
# Explicit human scope in this chat. Never infer ownership from --actor, branch
# name, main membership, or a caller-supplied list of supposedly owned releases.
OWN_FAILED_RELEASES = frozenset({"e7e1d28e0076f9981b8bf135cfc1f42eb90c353f"})
_SHA = re.compile(r"[0-9a-f]{40}")
_DEPENDENCY_ROOTS = (
    ".agents/scripts/",
    ".agents/skills/",
    "tennis-wong-choi/scripts/",
    "tennis-wong-choi/src/",
    "tennis-wong-choi/launchd/",
)


def _dependency(path: str) -> bool:
    # Deliberate superset: native review imports domain adapters and engines.
    # Include new/removed files and mode changes, not only the entry scripts.
    # The preview and CLI dispatcher are not executed by any installer.
    return ((path.startswith(_DEPENDENCY_ROOTS) or "/" not in path)
            and "/tests/" not in path and not path.endswith(".md")
            and path not in {
                ".agents/skills/shared_wong_choi/installation_reconciliation.py",
                ".agents/skills/central_wong_choi/scripts/central_wong_choi.py",
            })


def changed_installation_dependencies(repo: Path, source: str, target: str) -> list[str]:
    changes = _run(repo, "git", "diff", "--name-only", "--no-renames", "-z",
                   source, target, "--").stdout.split("\0")
    return sorted(path for path in changes if path and _dependency(path))


def _remote(repo: Path, ref: str) -> str:
    # ls-remote is read-only and checks the server, not a possibly stale local
    # tracking ref. Use full refs so branch names cannot be interpreted as flags.
    result = _run(repo, "git", "ls-remote", "--exit-code", "origin", ref)
    lines = result.stdout.splitlines()
    if len(lines) != 1 or len(lines[0].split()) != 2:
        raise ReleaseError(f"remote ref is missing or ambiguous: {ref}")
    sha, actual = lines[0].split()
    if actual != ref or not _SHA.fullmatch(sha):
        raise ReleaseError(f"invalid remote ref: {ref}")
    return sha


def _provenance(state: Path, commit: str, *, failed: bool) -> dict:
    _, manifest = _load_release(state / "releases", commit)
    events = []
    folder = state / "release-events" / quote(manifest["release_id"], safe="._-")
    # Status projections deliberately tolerate damaged records. Eligibility
    # cannot: silently dropping a rejection/failure can resurrect an approval.
    for path in sorted(folder.glob("*.json")):
        try:
            if path.is_symlink():
                raise ValueError("event is a symlink")
            value = json.loads(path.read_text(encoding="utf-8"))
            digest = value.pop("content_hash")
            stamp = datetime.fromisoformat(value["created_at"])
            if (digest != _hash(value) or value.get("schema_version") != EVENT_SCHEMA
                    or value.get("release_id") != manifest["release_id"]
                    or value.get("commit") != commit
                    or value.get("event_type") not in EVENT_TYPES
                    or not isinstance(value.get("detail"), dict)
                    or not isinstance(value.get("actor"), str) or not value["actor"].strip()
                    or stamp.tzinfo is None or stamp.utcoffset() is None):
                raise ValueError("event identity/schema/hash mismatch")
            expected_name = f"{stamp.strftime('%Y%m%dT%H%M%S.%fZ')}-{digest[:16]}.json"
            if path.name != expected_name:
                raise ValueError("event filename differs from hashed timestamp/content")
            value["content_hash"] = digest
            events.append(value)
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            raise ReleaseError(f"invalid release event: {path.name}") from exc
    events.sort(key=lambda event: (datetime.fromisoformat(event["created_at"]), event["content_hash"]))
    effective = effective_status(manifest, events)
    if effective["status"] != "merged" or not effective["approved"]:
        raise ReleaseError("release lacks existing merged approval provenance")
    if manifest.get("check_exit_code") != 0 or manifest.get("push_exit_code") != 0:
        raise ReleaseError("release lacks successful source gate/push provenance")
    gate = manifest.get("gate") or {}
    if gate.get("commit") != commit or gate.get("check") != "full":
        raise ReleaseError("release lacks exact-SHA full source gate provenance")
    if manifest.get("policy", {}).get("risk") in {"model", "evaluation"}:
        raise ReleaseError("model/evaluation release cannot be reconciled")
    approvals = {e["content_hash"] for e in events if e["event_type"] == "approval_granted"}
    merges = [e for e in events if e["event_type"] == "merged"]
    if not merges or merges[-1]["detail"].get("approval_event") not in approvals:
        raise ReleaseError("merge lacks linked immutable approval")
    if failed:
        plan = manifest.get("activation_plan") or {}
        if (effective["activation"] not in {"failed", "rolled_back"}
                or plan.get("installers") != [INSTALLER]
                or set(plan.get("production_sync_domains") or []) != set(DOMAINS)
                or plan.get("manual_required") or plan.get("dashboard_deploy")):
            raise ReleaseError("source is not a failed four-domain installer intent")
    else:
        successes = [e for e in events if e["event_type"] == "activation_succeeded"]
        if effective["activation"] != "succeeded" or not successes:
            raise ReleaseError("target lacks existing successful deployment provenance")
        verified = successes[-1]["detail"].get("verification") or []
        if {item.get("domain") for item in verified
                if item.get("status") == "aligned" and item.get("target_commit") == commit} != set(DOMAINS):
            raise ReleaseError("target lacks four-domain exact-SHA deployment provenance")
    return manifest


def _observe_installation_reconciliation(
    repo: Path, state_root: Path, *, source_commit: str, target_commit: str,
    production_roots: Mapping[str, Path], review_request: bool = False,
) -> dict:
    """Observe structural provenance; pending review never grants gate eligibility."""
    result = {"schema_version": "wong-choi-installation-preview/v1",
              "source_commit": source_commit, "target_commit": target_commit,
              "status": "blocked", "activation": "not_started",
              "installation_authorized": False, "fresh_full_gate_required": True,
              "independent_approval_required": True}
    try:
        if not all(_SHA.fullmatch(value) for value in (source_commit, target_commit)):
            raise ReleaseError("full immutable source and target SHAs are required")
        if source_commit not in OWN_FAILED_RELEASES:
            raise ReleaseError("source release is outside this chat's explicit authority")
        repo = repo.expanduser().resolve()
        if _remote(repo, "refs/heads/main") != target_commit:
            raise ReleaseError("current remote main differs from explicit target")
        if not _is_ancestor(repo, source_commit, target_commit):
            raise ReleaseError("source release is not an ancestor of the target")
        source = _provenance(state_root, source_commit, failed=True)
        changes = changed_installation_dependencies(repo, source_commit, target_commit)
        result["changed_dependencies"] = changes
        target = _provenance(state_root, target_commit, failed=False)
        for manifest in (source, target):
            branch = manifest.get("branch")
            if not isinstance(branch, str) or not branch or "\n" in branch:
                raise ReleaseError("manifest release branch is invalid")
            if _remote(repo, "refs/heads/" + branch) != manifest["commit"]:
                raise ReleaseError("remote release branch moved from immutable commit")
        if set(production_roots) != set(DOMAINS):
            raise ReleaseError("all four production roots must be explicit")
        roots = {Path(root).expanduser().resolve() for root in production_roots.values()}
        if len(roots) != 1:
            raise ReleaseError("unified installer requires one shared production checkout")
        for root in roots:
            if _run(root, "git", "rev-parse", "HEAD").stdout.strip() != target_commit:
                raise ReleaseError("production moved from explicit target; never retarget")
            status = _run(root, "git", "status", "--porcelain", "-z",
                          "--untracked-files=all", "--no-renames", check=False)
            if status.returncode != 0:
                raise ReleaseError("production status probe failed; cleanliness unverified")
            dirty = {entry[3:] for entry in status.stdout.split("\0") if entry}
            unexpected = dirty - EXPECTED_MUTABLE_PATHS
            if unexpected:
                raise ReleaseError("production has unrelated concurrent writes: " + ", ".join(sorted(unexpected)))
        # Recheck remote state at the end of this read-only observation window.
        if _remote(repo, "refs/heads/main") != target_commit:
            raise ReleaseError("main moved during preview")
        if changes and not review_request:
            raise ReleaseError("installer/dependency bytes changed; independent review required")
        result.update(status="pending_independent_review" if review_request else "eligible_for_fresh_gate",
                      installers=[INSTALLER], source_release_id=source["release_id"],
                      target_release_id=target["release_id"])
    except ReleaseError as exc:
        result["error"] = str(exc)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, subprocess.SubprocessError) as exc:
        result["error"] = f"preview probe failed closed: {type(exc).__name__}"
    return result



def preview_installation_reconciliation(
    repo: Path, state_root: Path, *, source_commit: str, target_commit: str,
    production_roots: Mapping[str, Path],
) -> dict:
    """Read-only strict eligibility. Changed dependencies remain blocked."""
    return _observe_installation_reconciliation(
        repo, state_root, source_commit=source_commit, target_commit=target_commit,
        production_roots=production_roots)


def _review_git_bytes(repo: Path, *args: str) -> bytes:
    result = subprocess.run(['git', *args], cwd=repo, capture_output=True, timeout=60, check=False)
    if result.returncode:
        raise ReleaseError('cannot read immutable installation review material')
    return result.stdout


def installation_review_material(repo: Path, source: str, target: str) -> dict:
    """Exact Git path identity, object modes and binary bytes for changed runtime inputs."""
    if not all(_SHA.fullmatch(value) for value in (source, target)):
        raise ReleaseError('immutable review source/target SHAs are required')
    raw = _review_git_bytes(repo, 'diff', '--raw', '--no-renames', '--no-abbrev', '-z', source, target, '--')
    parts = raw.split(b'\0')
    if parts[-1] != b'' or (len(parts) - 1) % 2:
        raise ReleaseError('invalid raw review diff')
    inventory = []
    for index in range(0, len(parts) - 1, 2):
        header, path_bytes = parts[index:index + 2]
        path = path_bytes.decode('utf-8', errors='strict')
        if not path or path.startswith('/') or '..' in Path(path).parts:
            raise ReleaseError('invalid review path identity')
        if not _dependency(path):
            continue
        fields = header.decode('ascii').split()
        if (len(fields) != 5 or not fields[0].startswith(':') or fields[4] not in {'A','M','D','T'}):
            raise ReleaseError('unsupported runtime dependency change')
        old_mode, new_mode, old_object, new_object, change = fields
        old_mode = old_mode[1:]
        def object_info(mode, oid):
            if mode == '000000' and oid == '0' * 40:
                return None
            if mode not in {'100644', '100755', '120000'} or not _SHA.fullmatch(oid):
                raise ReleaseError('unsupported dependency object mode or identity')
            size = int(_review_git_bytes(repo, 'cat-file', '-s', oid))
            if not 0 <= size <= 16 * 1024 * 1024:
                raise ReleaseError('runtime dependency exceeds bounded review material limit')
            data = _review_git_bytes(repo, 'cat-file', 'blob', oid)
            if len(data) != size:
                raise ReleaseError('dependency object size changed')
            return {'mode': mode, 'object_id': oid, 'bytes': size,
                    'sha256': hashlib.sha256(data).hexdigest()}
        inventory.append({'path': path, 'change': change,
                          'before': object_info(old_mode, old_object),
                          'after': object_info(new_mode, new_object)})
    inventory.sort(key=lambda item: item['path'])
    expected = changed_installation_dependencies(repo, source, target)
    if [item['path'] for item in inventory] != expected:
        raise ReleaseError('review inventory differs from conservative dependency scope')
    patch = (_review_git_bytes(repo, '--literal-pathspecs', 'diff', '--binary', '--full-index', '--no-ext-diff',
                              '--no-textconv', '--no-renames', source, target, '--', *expected)
             if expected else b'')
    return {'source_tree': _review_git_bytes(repo, 'rev-parse', source + '^{tree}').decode().strip(),
            'target_tree': _review_git_bytes(repo, 'rev-parse', target + '^{tree}').decode().strip(),
            'dependencies': inventory, 'inventory_hash': _hash({'dependencies': inventory}),
            'patch_sha256': hashlib.sha256(patch).hexdigest(), 'patch_bytes': len(patch)}


def create_installation_review_request(
    repo: Path, state_root: Path, *, source_commit: str, target_commit: str,
    production_roots: Mapping[str, Path], actor: str,
) -> dict:
    """Append nonauthorizing pending review material; never create an execution intent."""
    if not isinstance(actor, str) or not actor.strip():
        raise ReleaseError('installation review requester is required')
    options = dict(source_commit=source_commit, target_commit=target_commit,
                   production_roots=production_roots, review_request=True)
    observation = _observe_installation_reconciliation(repo, state_root, **options)
    if observation['status'] != 'pending_independent_review':
        raise ReleaseError(observation.get('error', 'installation review request blocked'))
    def intent_binding():
        return {'source_commit': source_commit, 'target_commit': target_commit,
                'source_release_id': observation['source_release_id'],
                'target_release_id': observation['target_release_id'],
                'manifest_hashes': {commit: hashlib.sha256(
                    _load_release(state_root / 'releases', commit)[0].read_bytes()).hexdigest()
                    for commit in (source_commit, target_commit)},
                'production_roots': {domain: str(Path(root).expanduser().resolve())
                                     for domain, root in sorted(production_roots.items())},
                'rollback_commit': target_commit, 'installers': [INSTALLER]}
    binding = intent_binding()
    material = installation_review_material(repo, source_commit, target_commit)
    value = {'schema_version': 'wong-choi-installation-review-request/v1',
             'created_at': datetime.now(timezone.utc).isoformat(), 'actor': actor.strip(),
             'status': 'pending_independent_review', 'intent_binding': binding,
             'intent_binding_hash': _hash(binding), 'material': material,
             'installation_authorized': False, 'gate_authorized': False,
             'assessment_authenticated': False, 'execution_intent_created': False}
    # Reobserve refs, event provenance, roots, manifests and all exact review
    # bytes immediately before create-only publication. Never silently retarget.
    if (_observe_installation_reconciliation(repo, state_root, **options) != observation
            or installation_review_material(repo, source_commit, target_commit) != material
            or intent_binding() != binding):
        raise ReleaseError('installation review bindings changed during preparation')
    value['content_hash'] = _hash(value)
    return _append_installation_record(state_root / 'installation-review-requests', value)

def create_installation_intent(
    repo: Path, state_root: Path, *, source_commit: str, target_commit: str,
    production_roots: Mapping[str, Path], actor: str,
) -> dict:
    """Append a request for fresh gates using current verified eligibility."""
    if not isinstance(actor, str) or not actor.strip():
        raise ReleaseError("installation intent actor is required")
    eligibility = preview_installation_reconciliation(
        repo, state_root, source_commit=source_commit, target_commit=target_commit,
        production_roots=production_roots)
    if eligibility["status"] != "eligible_for_fresh_gate":
        raise ReleaseError(eligibility.get("error", "installation eligibility blocked"))
    # Hash the immutable manifests as well as binding their release IDs. A later
    # gate/executor must reobserve eligibility and compare these exact bytes.
    manifests = {
        commit: hashlib.sha256(_load_release(state_root / "releases", commit)[0].read_bytes()).hexdigest()
        for commit in (source_commit, target_commit)
    }
    payload = {
        "schema_version": "wong-choi-installation-intent/v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "actor": actor.strip(),
        "source_commit": source_commit, "target_commit": target_commit,
        "source_release_id": eligibility["source_release_id"],
        "target_release_id": eligibility["target_release_id"],
        "manifest_hashes": manifests,
        "production_roots": {domain: str(Path(root).expanduser().resolve())
                             for domain, root in sorted(production_roots.items())},
        "rollback_commit": target_commit,
        "installers": [INSTALLER],
        "status": "pending_fresh_gate",
        "installation_authorized": False,
        "fresh_full_gate_required": True,
        "independent_approval_required": True,
    }
    if preview_installation_reconciliation(
            repo, state_root, source_commit=source_commit, target_commit=target_commit,
            production_roots=production_roots) != eligibility:
        raise ReleaseError("installation eligibility changed during intent preparation")
    payload["content_hash"] = _hash(payload)
    folder = state_root.expanduser().absolute() / "installation-intents"
    return _append_installation_record(folder, payload)


def _append_installation_record(folder: Path, payload: dict) -> dict:
    if any(path.is_symlink() for path in (folder, *folder.parents)):
        raise ReleaseError("installation intent directory is symlinked")
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not folder.is_dir():
        raise ReleaseError("installation intent directory is invalid")
    destination = folder / (payload["content_hash"] + ".json")
    descriptor, name = tempfile.mkstemp(prefix=".intent-", dir=folder)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w") as handle:
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, destination)  # Never replace an existing intent.
        directory = os.open(folder, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)
    return {**payload, "path": str(destination)}


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ReleaseError("duplicate installation intent field")
        result[key] = value
    return result


def load_installation_intent(repo: Path, state_root: Path, *, intent_hash: str,
                             production_roots: Mapping[str, Path]) -> dict:
    if not re.fullmatch("[0-9a-f]{64}", intent_hash):
        raise ReleaseError("full installation intent hash is required")
    path = state_root / "installation-intents" / (intent_hash + ".json")
    if any(parent.is_symlink() for parent in path.parents):
        raise ReleaseError("symlinked installation intent directory")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as handle:
        metadata = os.fstat(handle.fileno())
        if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid()
                or stat.S_IMODE(metadata.st_mode) != 0o600 or metadata.st_size > 65536):
            raise ReleaseError("unsafe installation intent file")
        raw = handle.read(65537)
    value = json.loads(raw, object_pairs_hook=_strict_object)
    fields = {"schema_version", "created_at", "actor", "source_commit", "target_commit",
              "source_release_id", "target_release_id", "manifest_hashes", "production_roots",
              "rollback_commit", "installers", "status", "installation_authorized",
              "fresh_full_gate_required", "independent_approval_required", "content_hash"}
    if (not isinstance(value, dict) or set(value) != fields
            or value["content_hash"] != intent_hash
            or _hash({k: v for k, v in value.items() if k != "content_hash"}) != intent_hash
            or value["schema_version"] != "wong-choi-installation-intent/v1"
            or value["status"] != "pending_fresh_gate"
            or value["installation_authorized"] is not False
            or value["fresh_full_gate_required"] is not True
            or value["independent_approval_required"] is not True
            or value["installers"] != [INSTALLER]
            or not isinstance(value["actor"], str) or not value["actor"].strip()):
        raise ReleaseError("installation intent binding is invalid")
    stamp = datetime.fromisoformat(value["created_at"])
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ReleaseError("installation intent time must be timezone-aware")
    preview = preview_installation_reconciliation(
        repo, state_root, source_commit=value["source_commit"], target_commit=value["target_commit"],
        production_roots=production_roots)
    if preview["status"] != "eligible_for_fresh_gate":
        raise ReleaseError(preview.get("error", "installation eligibility blocked"))
    roots = {domain: str(Path(root).expanduser().resolve())
             for domain, root in sorted(production_roots.items())}
    manifests = {commit: hashlib.sha256(
        _load_release(state_root / "releases", commit)[0].read_bytes()).hexdigest()
        for commit in (value["source_commit"], value["target_commit"])}
    if (value["production_roots"] != roots or value["manifest_hashes"] != manifests
            or value["rollback_commit"] != value["target_commit"]
            or value["source_release_id"] != preview["source_release_id"]
            or value["target_release_id"] != preview["target_release_id"]):
        raise ReleaseError("installation intent differs from current verified evidence")
    return value


def gate_installation_intent(repo: Path, state_root: Path, *, intent_hash: str,
                             production_roots: Mapping[str, Path]) -> dict:
    from .release_approval import _run_gate_in_clean_clone
    from .release_automation import _queued_release_lock
    from .release_gate import GateReceipt

    intent = load_installation_intent(repo, state_root, intent_hash=intent_hash,
                                      production_roots=production_roots)
    manifest = {"commit": intent["target_commit"], "release_id": "installation:" + intent_hash,
                "message": "forward installation full gate"}
    with _queued_release_lock(state_root, manifest=manifest):
        intent = load_installation_intent(repo, state_root, intent_hash=intent_hash,
                                          production_roots=production_roots)
        receipt = _run_gate_in_clean_clone(repo, intent["target_commit"], "full")
        if (not isinstance(receipt, GateReceipt) or receipt.commit != intent["target_commit"]
                or receipt.check != "full"):
            raise ReleaseError("fresh full installation gate receipt is invalid")
        if load_installation_intent(repo, state_root, intent_hash=intent_hash,
                                    production_roots=production_roots) != intent:
            raise ReleaseError("installation intent changed during the full gate")
        result = {
            "schema_version": "wong-choi-installation-gate/v1",
            "intent_hash": intent_hash, "target_commit": receipt.commit,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "full_gate_observed", "installation_authorized": False,
            "independent_approval_required": True,
            "elapsed_seconds": receipt.elapsed_seconds, "log": receipt.log,
        }
        result["content_hash"] = _hash(result)
        return _append_installation_record(
            state_root / "installation-gates" / intent_hash, result)


def _require_installation_review(intent: dict) -> None:
    # Exact-source review binding is not implemented yet. No actor text, saved
    # gate record or historical approval may enable the native executor.
    raise ReleaseError("exact-source installation review binding unavailable; native execution disabled")


def execute_installation_intent(repo: Path, state_root: Path, *, intent_hash: str,
                                production_roots: Mapping[str, Path], actor: str) -> dict:
    """Fresh in-process gates and one claimed native attempt; never sync/reset Git.

    A saved gate observation grants no authority. Existing preview provenance and
    dependency review blocks apply at every recheck. Attempts are never replayed,
    including after interruption or a failed outcome append.
    """
    from .deployment_verify import verify_deployment
    from .release_activation import _run_installer, _command_failure
    from .release_approval import _run_gate_in_clean_clone
    from .release_automation import _queued_release_lock
    from .release_gate import GateReceipt
    from .runtime_cutover_lease import cutover_lease, lease_path

    if not isinstance(actor, str) or not actor.strip():
        raise ReleaseError("installation executor actor is required")
    if repo.expanduser().resolve() != Path(__file__).resolve().parents[3]:
        raise ReleaseError("executor must run from its own exact approved checkout")
    # These native overrides are useful for isolated installer tests, never for
    # production acceptance through this controller.
    overrides = {key for key in os.environ if key in {
        "WC_RUNTIME_NO_PROBE", "WC_ALLOW_AU_BOT_UNLOADED", "WC_LAUNCHCTL_BIN",
        "WC_LAUNCH_AGENTS_DIR", "WC_RUNTIME_CUTOVER_FD",
        "WC_RUNTIME_INSTALL_SNAPSHOT", "WC_RUNTIME_EXPECTED_COMMIT"}}
    if overrides:
        raise ReleaseError("native executor overrides are forbidden: " + ", ".join(sorted(overrides)))
    if lease_path().parent.resolve() != state_root.expanduser().resolve():
        raise ReleaseError("executor and runtime cutover control roots differ")
    intent = load_installation_intent(repo, state_root, intent_hash=intent_hash,
                                      production_roots=production_roots)
    _require_installation_review(intent)
    target = intent["target_commit"]
    serial = {"commit": target, "release_id": "installation:" + intent_hash,
              "message": "forward installation execution"}

    def recheck():
        if load_installation_intent(repo, state_root, intent_hash=intent_hash,
                                    production_roots=production_roots) != intent:
            raise ReleaseError("installation intent/evidence changed")
        # The controller itself must run from the approved immutable source.
        if _run(repo, "git", "rev-parse", "HEAD").stdout.strip() != target:
            raise ReleaseError("executor source is not the exact approved target")
        status = _run(repo, "git", "status", "--porcelain", "-z",
                      "--untracked-files=all", check=False)
        if status.returncode != 0 or status.stdout:
            raise ReleaseError("executor source is not clean")

    with _queued_release_lock(state_root, manifest=serial):
        recheck()
        attempts = state_root / "installation-attempts"
        if any(path.is_symlink() for path in (attempts, *attempts.parents)):
            raise ReleaseError("unsafe installation attempt directory")
        attempt = attempts / intent_hash
        if attempt.exists() or attempt.is_symlink():
            raise ReleaseError("installation attempt already claimed; automatic replay forbidden")
        full = _run_gate_in_clean_clone(repo, target, "full")
        if not isinstance(full, GateReceipt) or not full.reusable(repo, target, "full"):
            raise ReleaseError("fresh full installation receipt is invalid")
        recheck()
        approval = _run_gate_in_clean_clone(repo, target, "quick")
        if (not isinstance(approval, GateReceipt) or approval.commit != target
                or approval.check != "quick" or approval.environment != full.environment
                or not full.reusable(repo, target, "full")
                or not approval.reusable(repo, target, "quick")):
            raise ReleaseError("independent clean installation approval is invalid")
        recheck()
        def receipts_current():
            if not full.reusable(repo, target, "full") or not approval.reusable(repo, target, "quick"):
                raise ReleaseError("installation gate/approval freshness expired")

        def recovery_source_current():
            # Recovery is local and ownership-bound; a remote outage or moved
            # main cannot revoke recovery of this attempt's native writes.
            production = next(iter(production_roots.values())).expanduser().resolve()
            if _run(production, "git", "rev-parse", "HEAD").stdout.strip() != target:
                raise ReleaseError("recovery installer checkout moved")
            status = _run(production, "git", "status", "--porcelain", "-z",
                          "--untracked-files=all", "--no-renames", check=False)
            dirty = {entry[3:] for entry in status.stdout.split("\0") if entry}
            if status.returncode or dirty - EXPECTED_MUTABLE_PATHS:
                raise ReleaseError("recovery native source changed or unverified")

        # Continuous cooperative exclusion across snapshot/install/status/restore.
        with cutover_lease("exclusive") as fd:
            recheck()
            receipts_current()
            _require_installation_review(intent)
            attempts.mkdir(mode=0o700, parents=True, exist_ok=True)
            attempt.mkdir(mode=0o700)  # Atomic one-attempt claim, never removed.
            parent = os.open(attempts, os.O_RDONLY)
            try:
                os.fsync(parent)
            finally:
                os.close(parent)

            def record(status, **detail):
                value = {"schema_version": "wong-choi-installation-attempt/v1",
                         "intent_hash": intent_hash, "target_commit": target,
                         "rollback_commit": target, "actor": actor.strip(),
                         "created_at": datetime.now(timezone.utc).isoformat(),
                         "status": status, **detail}
                value["content_hash"] = _hash(value)
                return _append_installation_record(attempt, value)

            record("approval_observed", full_log=full.log, approval_log=approval.log)
            production = next(iter(production_roots.values())).expanduser().resolve()
            installer = production / INSTALLER
            snapshot = attempt / "native-snapshot"
            mutation_started = False
            try:
                recheck()
                result = _run_installer(production, "/bin/zsh", str(installer),
                                        "--snapshot", str(snapshot), timeout=120, lease_fd=fd)
                if result.returncode:
                    raise _command_failure("forward installation snapshot failed", result)
                record("snapshot_captured", snapshot=str(snapshot))
                recheck()  # Detect changes between the outer observation and install.
                receipts_current()
                _require_installation_review(intent)
                record("installation_started", snapshot=str(snapshot))
                mutation_started = True
                result = _run_installer(
                    production, "/bin/zsh", str(installer), "--install-from-snapshot",
                    str(snapshot), "--expected-commit", target, timeout=300, lease_fd=fd)
                if result.returncode:
                    raise _command_failure("forward installation failed", result)
                recheck()
                result = _run_installer(production, "/bin/zsh", str(installer),
                                        "--status", timeout=60, lease_fd=fd)
                if result.returncode:
                    raise _command_failure("forward installed/loaded verification failed", result)
                # Compare all required files to a detached exact-SHA source.
                with tempfile.TemporaryDirectory(prefix="wc-forward-verify-") as raw:
                    clean = Path(raw) / "source"
                    _run(repo, "git", "clone", "--shared", "--no-checkout", str(repo), str(clean))
                    _run(clean, "git", "checkout", "--detach", target)
                    verification = []
                    for domain in DOMAINS:
                        checked = verify_deployment(clean, Path(production_roots[domain]), domain)
                        if not checked["safe_to_activate"] or checked["target_commit"] != target:
                            raise ReleaseError("forward required-file verification failed: " + domain)
                        verification.append({"domain": domain, "status": checked["status"],
                                             "target_commit": target})
                recheck()
                accepted = _run_installer(production, "/bin/zsh", str(installer),
                                         "--acceptance-status", str(snapshot), timeout=60, lease_fd=fd)
                if accepted.returncode:
                    raise _command_failure("forward calendar/native receipt acceptance failed", accepted)
                recheck()
                return record("installed_verified", verification=verification,
                              snapshot=str(snapshot), native_acceptance_verified=True)
            except BaseException as exc:
                recovery = "not_needed"
                error = None
                if mutation_started:
                    recovery = "blocked"
                    try:
                        # Do not execute a foreign replacement installer on rollback.
                        recovery_source_current()
                        restored = _run_installer(production, "/bin/zsh", str(installer),
                                                  "--restore", str(snapshot), timeout=300, lease_fd=fd)
                        if restored.returncode:
                            raise _command_failure("forward native restore failed", restored)
                        recovery = "restored"
                    except BaseException as restore_exc:
                        error = f"{type(restore_exc).__name__}: {restore_exc}"
                try:
                    record("failed", error=f"{type(exc).__name__}: {exc}", recovery=recovery,
                           recovery_error=error, snapshot=str(snapshot), evidence_retained=True)
                except BaseException as append_exc:
                    raise ReleaseError(f"forward outcome unavailable; attempt/evidence retained at {attempt}") from append_exc
                raise ReleaseError(f"forward installation failed; recovery {recovery}; evidence retained at {attempt}") from exc
