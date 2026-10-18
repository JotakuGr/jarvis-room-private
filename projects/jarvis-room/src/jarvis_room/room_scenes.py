"""Expande cenas/grupos em planos imutáveis; nenhuma ação é executada aqui."""

from dataclasses import dataclass, field
from pathlib import Path

from ._offline_json import load_object
from .room_device_registry import DEFAULT_PATH as CATALOG_PATH, GROUPS, RoomRegistryError, load_room_devices, valid_id
from .room_intent import RoomIntent, parse_room_intent

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "room_scenes.json"


class RoomPlanError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SceneStep:
    id: str
    target_kind: str
    target_id: str
    action: str
    depends_on: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RoomScene:
    id: str
    operation: str
    steps: tuple[SceneStep, ...]


@dataclass(frozen=True, slots=True)
class PlannedAction:
    device_id: str
    action: str
    depends_on: tuple[str, ...]
    capability_supported: bool
    integration_status: str
    execution_available: bool = field(default=False, init=False)


@dataclass(frozen=True, slots=True)
class ExecutionPlan:
    intent: RoomIntent
    steps: tuple[PlannedAction, ...]
    physical_control_enabled: bool = field(default=False, init=False)


def _ordered(nodes: dict[str, tuple[str, ...]]) -> tuple[str, ...]:
    pending, done = list(nodes), []
    if any(ref not in nodes for refs in nodes.values() for ref in refs):
        raise RoomPlanError("unknown_dependency")
    while pending:
        ready = [key for key in pending if set(nodes[key]) <= set(done)]
        if not ready:
            raise RoomPlanError("cyclic_dependencies")
        for key in ready:
            done.append(key)
            pending.remove(key)
    return tuple(done)


def _targets(kind, identifier, devices):
    if kind == "device":
        if identifier not in devices:
            raise RoomPlanError("unknown_device")
        return (identifier,)
    if kind != "group" or identifier not in GROUPS:
        raise RoomPlanError("unknown_group")
    targets = tuple(d.id for d in devices.values() if d.group == identifier)
    if not targets:
        raise RoomPlanError("empty_group")
    return targets


def load_room_scenes(path: Path = DEFAULT_PATH, catalog_path: Path = CATALOG_PATH) -> dict[str, RoomScene]:
    try:
        devices = load_room_devices(catalog_path)
        data = load_object(path, ValueError)
        if (set(data) != {"schema_version", "mode", "scenes"} or type(data["schema_version"]) is not int
            or data["schema_version"] != 1 or data["mode"] != "offline"
            or type(data["scenes"]) is not list or not 1 <= len(data["scenes"]) <= 32):
            raise ValueError()
        scenes = {}
        for raw in data["scenes"]:
            if (type(raw) is not dict or set(raw) != {"id", "operation", "steps"}
                or not valid_id(raw["id"]) or raw["id"] in scenes
                or raw["operation"] not in ("activate", "deactivate")
                or type(raw["steps"]) is not list or not 1 <= len(raw["steps"]) <= 32):
                raise ValueError()
            if raw["id"] in ("modo_apresentacao", "encerrar_apresentacao") and raw["operation"] != (
                "activate" if raw["id"] == "modo_apresentacao" else "deactivate"
            ):
                raise ValueError()
            steps = {}
            for item in raw["steps"]:
                if (type(item) is not dict or set(item) != {"id", "target_kind", "target_id", "action", "depends_on"}
                    or not valid_id(item["id"]) or item["id"] in steps or not valid_id(item["target_id"])
                    or item["action"] != ("turn_on" if raw["operation"] == "activate" else "turn_off")
                    or type(item["depends_on"]) is not list or len(item["depends_on"]) > 32
                    or any(not valid_id(ref) for ref in item["depends_on"])
                    or len(set(item["depends_on"])) != len(item["depends_on"])):
                    raise ValueError()
                _targets(item["target_kind"], item["target_id"], devices)
                steps[item["id"]] = SceneStep(**{**item, "depends_on": tuple(item["depends_on"])})
            order = _ordered({key: step.depends_on for key, step in steps.items()})
            scenes[raw["id"]] = RoomScene(raw["id"], raw["operation"], tuple(steps[key] for key in order))
        return scenes
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        raise RoomPlanError("scene_configuration_unavailable") from None


def build_room_plan(intent: RoomIntent, catalog_path: Path = CATALOG_PATH,
                    scenes_path: Path = DEFAULT_PATH) -> ExecutionPlan:
    try:
        if (type(intent) is not RoomIntent or intent.recognized is not True
            or parse_room_intent(intent.phrase, catalog_path) != intent):
            raise RoomPlanError("invalid_intent")
        devices = load_room_devices(catalog_path)
        if intent.kind != "scene_control":
            targets = _targets("group" if intent.kind == "group_control" else "device", intent.target_id, devices)
            return ExecutionPlan(intent, tuple(PlannedAction(
                identifier, intent.action, (), intent.action in devices[identifier].capabilities,
                devices[identifier].integration_status,
            ) for identifier in targets))
        scenes = load_room_scenes(scenes_path, catalog_path)
        scene = scenes.get(intent.target_id)
        if scene is None or scene.operation != intent.action:
            raise RoomPlanError("unknown_scene")
        expanded = {step.id: _targets(step.target_kind, step.target_id, devices) for step in scene.steps}
        actions, dependencies = {}, {}
        for step in scene.steps:
            for identifier in expanded[step.id]:
                if identifier in actions and actions[identifier] != step.action:
                    raise RoomPlanError("conflicting_actions")
                actions[identifier] = step.action
                refs = dependencies.setdefault(identifier, [])
                for dep in step.depends_on:
                    for member in expanded[dep]:
                        # Mesma ação duplicada é executada uma única vez.
                        if member != identifier and member not in refs:
                            refs.append(member)
        order = _ordered({key: tuple(refs) for key, refs in dependencies.items()})
        return ExecutionPlan(intent, tuple(PlannedAction(
            key, actions[key], tuple(dependencies[key]), actions[key] in devices[key].capabilities,
            devices[key].integration_status,
        ) for key in order))
    except RoomRegistryError:
        raise RoomPlanError("room_catalog_unavailable") from None
