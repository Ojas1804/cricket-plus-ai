"""Deterministic resolution of user-provided names to canonical database entities."""
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.cricket.models import BattingPerformance, BowlingPerformance, Competition, Player, Team, Venue

DOMINANCE_RATIO = 10
DOMINANCE_MIN_INNINGS = 50


class EntityResolutionError(Exception):
    def __init__(self, entity_type: str, mention: str, options: list[str]) -> None:
        self.entity_type, self.mention, self.options = entity_type, mention, options
        super().__init__(f"{entity_type} '{mention}'")


class UnknownEntity(EntityResolutionError):
    pass


class AmbiguousEntity(EntityResolutionError):
    pass


@dataclass
class Resolution:
    value: int | str
    label: str
    notes: list[str] = field(default_factory=list)


def _is_initials(token: str) -> bool:
    return token.isupper() and len(token) <= 4


def _given_compatible(cand_given: list[str], mention_given: list[str]) -> bool:
    for c, g in zip(cand_given, mention_given):
        if _is_initials(c):
            if c[0].lower() != g[0].lower():
                return False
        elif not (g.lower().startswith(c.lower()) or c.lower().startswith(g.lower())):
            return False
    return True


def _innings_counts(session: Session, ids: list[int]) -> dict[int, int]:
    counts = {i: 0 for i in ids}
    for model in (BattingPerformance, BowlingPerformance):
        for pid, n in session.execute(select(model.player_id, func.count()).where(model.player_id.in_(ids)).group_by(model.player_id)):
            counts[pid] += n
    return counts


def resolve_player(session: Session, mention: str) -> Resolution:
    text = " ".join(mention.split())
    if not text:
        raise UnknownEntity("player", mention, [])
    exact = session.scalars(select(Player).where(
        (func.lower(Player.display_name) == text.lower()) | (func.lower(Player.full_name) == text.lower()))).all()
    if len(exact) == 1:
        return Resolution(exact[0].id, exact[0].display_name)

    tokens = text.split()
    surname = tokens[-1].lower()
    rows = session.scalars(select(Player).where(
        (func.lower(Player.display_name) == surname) | func.lower(Player.display_name).like(f"% {surname}"))).all()
    cands = exact or [p for p in rows if _given_compatible(p.display_name.split()[:-1], tokens[:-1])]
    if not cands:
        raise UnknownEntity("player", mention, [])
    if len(cands) == 1:
        return Resolution(cands[0].id, cands[0].display_name)

    counts = _innings_counts(session, [p.id for p in cands])
    ranked = sorted(cands, key=lambda p: counts[p.id], reverse=True)
    top, second = counts[ranked[0].id], counts[ranked[1].id]
    if top >= DOMINANCE_MIN_INNINGS and top >= DOMINANCE_RATIO * max(second, 1):
        others = ", ".join(p.display_name for p in ranked[1:4])
        return Resolution(ranked[0].id, ranked[0].display_name,
                          [f"'{mention}' was resolved to {ranked[0].display_name} (most appearances); other matches: {others}"])
    raise AmbiguousEntity("player", mention, [p.display_name for p in ranked[:8]])


def _resolve_named(session: Session, model, mention: str, entity_type: str, acronyms: bool = False) -> Resolution:
    text = " ".join(mention.split())
    col = model.name
    exact = session.scalars(select(col).where(func.lower(col) == text.lower()).distinct()).all()
    if len(exact) == 1:
        return Resolution(exact[0], exact[0])
    pool: list[str] = list(exact)
    if not pool and acronyms and text.isalpha() and text.isupper():
        names = session.scalars(select(col).distinct()).all()
        pool = [n for n in names if "".join(w[0] for w in n.split() if w[0].isupper()) == text]
    if not pool:
        pool = list(session.scalars(select(col).where(func.lower(col).like(f"%{text.lower()}%")).distinct()).all())
    if not pool:
        raise UnknownEntity(entity_type, mention, [])
    if len(pool) == 1:
        return Resolution(pool[0], pool[0])
    raise AmbiguousEntity(entity_type, mention, sorted(pool)[:8])


def resolve_team(session: Session, mention: str) -> Resolution:
    return _resolve_named(session, Team, mention, "team")


def resolve_competition(session: Session, mention: str) -> Resolution:
    return _resolve_named(session, Competition, mention, "competition", acronyms=True)


def resolve_venue(session: Session, mention: str) -> Resolution:
    return _resolve_named(session, Venue, mention, "venue", acronyms=True)


RESOLVERS = {"team": resolve_team, "opposition": resolve_team, "competition": resolve_competition, "venue": resolve_venue}


def normalize_filter(session: Session, field_name: str, operator: str, value) -> tuple[str, str, object, list[str]]:
    """Resolve entity names in a filter to canonical values. Returns (field, operator, value, notes)."""
    values = value if isinstance(value, list) else [value]
    notes: list[str] = []
    if field_name == "player":
        res = [resolve_player(session, str(v)) for v in values]
        for r in res:
            notes.extend(r.notes)
        ids = [r.value for r in res]
        return "player_id", ("in" if len(ids) > 1 else "equals"), (ids if len(ids) > 1 else ids[0]), notes
    if field_name in RESOLVERS:
        res = [RESOLVERS[field_name](session, str(v)) for v in values]
        names = [r.value for r in res]
        return field_name, ("in" if len(names) > 1 else "equals"), (names if len(names) > 1 else names[0]), notes
    return field_name, operator, value, notes
