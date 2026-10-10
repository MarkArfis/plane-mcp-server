"""workitem_relation falls back to the pre-1.5 /relations/ route when the new ones are missing.

Plane Community <= 1.4.2 has no /dependencies/ or /work-item-relation-definitions/ route and answers
404 there; the older /relations/ route still works. These tests simulate such an instance.
"""

from __future__ import annotations

import pytest
from plane.errors.errors import PlaneError

from plane_mcp.tools import workitem_relation

P, W, T = "proj-1", "item-1", "item-2"


def _missing(*args, **kwargs):
    raise PlaneError("HTTP 404: Not Found", 404)


class _Recorder:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def rec(self, name):
        def call(**kwargs):
            self.calls.append((name, kwargs))
            return None

        return call

    def get(self, endpoint):
        self.calls.append(("relations._get", {"endpoint": endpoint}))
        return {"blocking": [], "blocked_by": [T]}


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
    client.work_items.relations.create = rec.rec("relations.create")
    client.work_items.relations.delete = rec.rec("relations.delete")
    client.work_item_relation_definitions = Ns()
    client.work_item_relation_definitions.list = _missing

    monkeypatch.setattr(workitem_relation, "get_plane_client_context", lambda: (client, "work"))
    return rec


def _tool(registered):
    return registered["workitem_relation"].fn


def test_create_falls_back_to_legacy_route(old_plane, registered):
    _tool(registered)(action="create", project_id=P, workitem_id=W, workitem_ids=[T], relation_type="blocked_by")
    name, kwargs = old_plane.calls[-1]
    assert name == "relations.create"
    assert kwargs["data"].relation_type == "blocked_by" and kwargs["data"].issues == [T]


def test_list_falls_back_to_legacy_route(old_plane, registered):
    result = _tool(registered)(action="list", project_id=P, workitem_id=W)
    assert result["dependencies"]["blocked_by"] == [T] and result["custom"] == {}
    assert old_plane.calls[-1][1]["endpoint"] == f"work/projects/{P}/work-items/{W}/relations"


def test_delete_falls_back_to_legacy_route(old_plane, registered):
    _tool(registered)(action="delete", project_id=P, workitem_id=W, related_workitem_id=T, is_dependency=True)
    name, kwargs = old_plane.calls[-1]
    assert name == "relations.delete" and kwargs["data"].related_issue == T


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
