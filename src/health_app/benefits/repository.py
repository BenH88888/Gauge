"""In-memory storage and the protocol that the API depends on.

The repository is split into a protocol and a concrete implementation so
that the API does not depend on a particular storage choice. Swapping in a
database-backed implementation later only requires conforming to the
protocol.
"""

from __future__ import annotations

from typing import Protocol

from health_app.benefits.models import Member, Plan, Procedure


class CatalogRepository(Protocol):
    """Read-only lookups for plans, members, and procedures."""

    def get_plan(self, plan_id: str) -> Plan | None: ...
    def get_member(self, member_id: str) -> Member | None: ...
    def get_procedure(self, code: str) -> Procedure | None: ...


class InMemoryRepository:
    """Trivial in-memory implementation used by the prototype."""

    def __init__(
        self,
        plans: list[Plan],
        members: list[Member],
        procedures: list[Procedure],
    ) -> None:
        self._plans: dict[str, Plan] = {p.plan_id: p for p in plans}
        self._members: dict[str, Member] = {m.member_id: m for m in members}
        self._procedures: dict[str, Procedure] = {
            p.code: p for p in procedures
        }

    def get_plan(self, plan_id: str) -> Plan | None:
        return self._plans.get(plan_id)

    def get_member(self, member_id: str) -> Member | None:
        return self._members.get(member_id)

    def get_procedure(self, code: str) -> Procedure | None:
        return self._procedures.get(code)
