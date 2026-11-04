"""Keep TE's source actor namespace separate from global display-name aliases."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import re
from urllib.parse import urlsplit

from tennis_wc.features.common import utc_now
from tennis_wc.identity import player_identity
from tennis_wc.ingestion.name_matching import normalise_player_name, player_name_score


PROVIDER = 'tennisexplorer'


class SourceActorHold(ValueError):
    """The source cannot safely be attached to an existing player."""


def canonical_actor_ref(ref: str | None) -> str | None:
    if not isinstance(ref, str):
        return None
    try:
        parsed = urlsplit(ref)
    except ValueError:
        return None
    if (parsed.scheme != 'https' or parsed.netloc != 'www.tennisexplorer.com'
            or parsed.query or parsed.fragment
            or not re.fullmatch(r'/player/[A-Za-z0-9][A-Za-z0-9_-]*/?', parsed.path)):
        return None
    return 'https://www.tennisexplorer.com' + parsed.path.rstrip('/') + '/'


def _available(binding) -> bool:
    try:
        created = datetime.fromisoformat(binding['created_at'].replace('Z', '+00:00'))
        updated = datetime.fromisoformat(binding['updated_at'].replace('Z', '+00:00'))
        return (created.utcoffset() is not None and updated.utcoffset() is not None
                and created <= updated <= datetime.now(timezone.utc))
    except (ValueError, TypeError, AttributeError):
        return False


def _full(tokens: list[str]) -> bool:
    return len(tokens) >= 2 and all(len(token) > 1 for token in tokens)


def _labels_agree(left: str, right: str) -> bool:
    a, b = normalise_player_name(left).split(), normalise_player_name(right).split()
    if not a or not b:
        return False
    if sorted(a) == sorted(b):
        return True
    # A source binding has already chosen the actor here. Initials only check
    # its display label; they never select a global identity.
    if _full(a) and _full(b):
        return False
    common = Counter(a) & Counter(b)
    if not any(len(token) > 1 for token in common):
        return False
    remaining_a, remaining_b = Counter(a) - common, Counter(b) - common

    def abbreviates(short, long):
        initials = Counter()
        for token, count in long.items():
            initials[token[0]] += count
        return all(len(token) == 1 and count <= initials[token]
                   for token, count in short.items())

    return abbreviates(remaining_a, remaining_b) or abbreviates(remaining_b, remaining_a)


def _player(conn, player_id: int):
    return conn.execute('SELECT id,name,tour,source_provider,canonical_player_id '
                        'FROM players WHERE id=?', (player_id,)).fetchone()


def _check_target(row, tour: str) -> None:
    if row is None:
        raise SourceActorHold('source_binding_target_missing')
    if row['canonical_player_id'] is not None:
        raise SourceActorHold('source_binding_target_moved')
    current = str(row['tour'] or '').upper()
    if current not in {'ATP', 'WTA'}:
        raise SourceActorHold('unknown_target_tour')
    if current != tour:
        raise SourceActorHold('target_tour_conflict')


def _other_bound_actor(conn, row, ref: str) -> bool:
    """Different explicit TE actor keys may legitimately share a display name."""
    if row is None or row['source_provider'] != PROVIDER or row['canonical_player_id'] is not None:
        return False
    bindings = conn.execute("SELECT * FROM provider_entities WHERE provider_name=? "
                            "AND entity_type='player' AND internal_entity_id=?",
                            (PROVIDER, row['id'])).fetchall()
    return bool(bindings) and all(
        canonical_actor_ref(b['provider_entity_id']) not in {None, ref}
        and _available(b) and _labels_agree(b['entity_name'], row['name'])
        for b in bindings
    )


def resolve_source_actor(conn, ref: str | None, name: str, tour: str, created: list) -> int:
    if not name or player_identity.is_placeholder(name):
        raise SourceActorHold('placeholder_player')
    tokens = normalise_player_name(name).split()
    if not tokens:
        raise SourceActorHold('invalid_player_name')
    ref = canonical_actor_ref(ref)
    if ref is None:
        raise SourceActorHold('invalid_source_actor')
    bindings = conn.execute("SELECT * FROM provider_entities WHERE provider_name=? "
                            "AND entity_type='player' AND provider_entity_id IN (?,?)",
                            (PROVIDER, ref, ref.rstrip('/'))).fetchall()
    if bindings:
        if len(bindings) != 1:
            raise SourceActorHold('source_binding_collision')
        binding = bindings[0]
        if not _available(binding):
            raise SourceActorHold('source_binding_not_available')
        row = _player(conn, binding['internal_entity_id'])
        _check_target(row, tour)
        target_tokens = normalise_player_name(row['name']).split()
        binding_tokens = normalise_player_name(binding['entity_name']).split()
        if ((_full(target_tokens) and not _full(binding_tokens))
                or not _labels_agree(binding['entity_name'], row['name'])
                or not _labels_agree(name, binding['entity_name'])):
            raise SourceActorHold('source_binding_name_conflict')
        return row['id']

    existing = player_identity.resolve_player_id(conn, name, tour)
    if existing is not None:
        row = _player(conn, existing)
        if not _other_bound_actor(conn, row, ref):
            _check_target(row, tour)
            raise SourceActorHold('unbound_source_actor')
    else:
        surname = tokens[-1]
        neighbors = conn.execute(
            'SELECT id,name,tour,source_provider,canonical_player_id FROM players '
            'WHERE LOWER(name) LIKE ? OR LOWER(name) LIKE ?',
            (f'%{surname}%', f'%{surname[:4]}%'),
        )
        if any(player_name_score(name, row['name']) >= 0.92
               and not _other_bound_actor(conn, row, ref) for row in neighbors):
            raise SourceActorHold('unresolved_existing_player')

    now = utc_now()
    cursor = conn.execute('INSERT INTO players(name,tour,source_provider,created_at,updated_at) '
                          'VALUES(?,?,?,?,?)', (name, tour, PROVIDER, now, now))
    player_id = int(cursor.lastrowid)
    conn.execute("INSERT INTO provider_entities(provider_name,entity_type,provider_entity_id,"
                 "internal_entity_id,entity_name,confidence_score,created_at,updated_at) "
                 "VALUES(?,'player',?,?,?,1,?,?)", (PROVIDER, ref, player_id, name, now, now))
    # A source display label is not a global cross-provider alias.
    created.append(player_id)
    return player_id
