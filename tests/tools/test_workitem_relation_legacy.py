"""workitem_relation falls back to the pre-1.5 /relations/ route when the new ones are missing.

Plane Community <= 1.4.2 has no /dependencies/ or /work-item-relation-definitions/ route and answers
404 there; the older /relations/ route still works. These tests simulate such an instance.
"""

from __future__ import annotations

import pytest
from plane.errors.errors import PlaneError

from plane_mcp.tools import workitem_relation

P, W, T, GHOST = "proj-1", "item-1", "item-2", "item-404"


def _missing(*args, **kwargs):
    raise PlaneError("HTTP 404: Not Found", 404)


class _Recorder:
    """Records calls and keeps the relations an old Plane would store: unknown ids are dropped silently."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.stored: dict[str, list[dict]] = {"blocking": [], "blocked_by": [T]}

    def rec(self, name):
        def call(**kwargs):
            self.calls.append((name, kwargs))
            return None

        return call

    def create(self, **kwargs):
        self.calls.append(("relations.create", kwargs))
        data = kwargs["data"]
        known = [i for i in data.issues if i != GHOST]
        self.stored.setdefault(data.relation_type, []).extend({"project_id": P, "issue_id": i} for i in known)
        return [{"id": i, "relation_type": data.relation_type} for i in known]

    def get(self, endpoint):
        self.calls.append(("relations._get", {"endpoint": endpoint}))
        return self.stored


@pytest.fixture
def old_plane(monkeypatch):
    rec = _Recorder()

    class Ns:
        pass

    client = Ns()
    client.work_items = Ns()
    client.work_items.dependencies = Ns()
    client.work_items.dependencies.list = _missing
    client.work_items.dependencies.create = _missing
    client.work_items.dependencies.remove = _missing
    client.work_items.custom_relations = Ns()
    client.work_items.custom_relations.list = _missing
    client.work_items.custom_relations.remove = _missing
    client.work_items.relations = Ns()
    client.work_items.relations._get = rec.get
    client.work_items.relations.create = rec.create
    client.work_items.relations.delete = rec.rec("relations.delete")
    client.work_item_relation_definitions = Ns()
    client.work_item_relation_definitions.list = _missing

    monkeypatch.setattr(workitem_relation, "get_plane_client_context", lambda: (client, "work"))
    return rec


def _tool(registered):
    return registered["workitem_relation"].fn


def _created(rec):
    return [kwargs for name, kwargs in rec.calls if name == "relations.create"]


def test_create_falls_back_to_legacy_route(old_plane, registered):
    result = _tool(registered)(
        action="create", project_id=P, workitem_id=W, workitem_ids=["item-3"], relation_type="blocking"
    )
    (kwargs,) = _created(old_plane)
    assert kwargs["data"].relation_type == "blocking" and kwargs["data"].issues == ["item-3"]
    assert result == [{"id": "item-3", "relation_type": "blocking"}]


@pytest.mark.parametrize("relation_type", ["relates_to", "duplicate"])
def test_legacy_only_types_are_accepted(old_plane, registered, relation_type):
    result = _tool(registered)(
        action="create", project_id=P, workitem_id=W, workitem_ids=["item-3"], relation_type=relation_type
    )
    (kwargs,) = _created(old_plane)
    assert kwargs["data"].relation_type == relation_type
    assert result == [{"id": "item-3", "relation_type": relation_type}]


def test_legacy_only_type_on_new_plane_explains_custom_relations(registered, monkeypatch):
    client = type("C", (), {})()
    client.work_items = type("W", (), {})()
    client.work_items.relations = type("R", (), {"create": staticmethod(_missing)})()
    monkeypatch.setattr(workitem_relation, "get_plane_client_context", lambda: (client, "work"))
    result = _tool(registered)(
        action="create", project_id=P, workitem_id=W, workitem_ids=[T], relation_type="relates_to"
    )
    assert result.startswith("Error:") and "relation_definition_id" in result


def test_unknown_relation_type_lists_legacy_types(old_plane, registered):
    result = _tool(registered)(action="create", project_id=P, workitem_id=W, workitem_ids=[T], relation_type="x")
    assert result.startswith("Error:") and "relates_to" in result and "duplicate" in result
    assert not _created(old_plane)


def test_create_reports_ids_plane_dropped(old_plane, registered):
    result = _tool(registered)(
        action="create", project_id=P, workitem_id=W, workitem_ids=["item-3", GHOST], relation_type="blocked_by"
    )
    assert result["not_created"] == [GHOST]
    assert result["created"] == [{"id": "item-3", "relation_type": "blocked_by"}]


def test_list_falls_back_to_legacy_route(old_plane, registered):
    result = _tool(registered)(action="list", project_id=P, workitem_id=W)
    assert result["dependencies"]["blocked_by"] == [T] and result["custom"] == {}
    assert old_plane.calls[-1][1]["endpoint"] == f"work/projects/{P}/work-items/{W}/relations"


def test_delete_falls_back_to_legacy_route(old_plane, registered):
    result = _tool(registered)(action="delete", project_id=P, workitem_id=W, related_workitem_id=T, is_dependency=True)
    name, kwargs = old_plane.calls[-1]
    assert name == "relations.delete" and kwargs["data"].related_issue == T
    assert result is None


@pytest.mark.parametrize("is_dependency", [True, False])
def test_delete_without_any_route_says_so(old_plane, registered, is_dependency):
    client, _ = workitem_relation.get_plane_client_context()
    client.work_items.relations.delete = _missing
    result = _tool(registered)(
        action="delete", project_id=P, workitem_id=W, related_workitem_id=T, is_dependency=is_dependency
    )
    assert result.startswith("Error:") and "web UI" in result and "Nothing was changed" in result


def test_list_definitions_survives_missing_endpoint(old_plane, registered):
    result = _tool(registered)(action="list_definitions")
    assert result["custom_definitions"] == [] and "blocked_by" in result["built_in_dependencies"]


def test_other_errors_are_not_swallowed(old_plane, registered, monkeypatch):
    def forbidden(**kwargs):
        raise PlaneError("HTTP 403: Forbidden", 403)

    client, _ = workitem_relation.get_plane_client_context()
    client.work_items.dependencies.create = forbidden
    with pytest.raises(PlaneError):
        _tool(registered)(action="create", project_id=P, workitem_id=W, workitem_ids=[T], relation_type="blocked_by")
    assert not old_plane.calls
