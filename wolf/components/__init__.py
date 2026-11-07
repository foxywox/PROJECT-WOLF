"""Swappable WOLF components.

Everything WOLF can do beyond talking comes from a component: memory, web search, the clock,
and anything added later (calendar, email, reminders...). Components are interchangeable:
the core never imports a specific one, so any of them can be turned off, replaced by another
implementation, or added without touching WOLF itself.

A component is a subclass of `Component` that may provide any of:
  tools()          client tools (built with `wolf.loop.tool`) and `call()` to run them
  server_tools()   Anthropic server tools (e.g. web search)
  instructions()   stable guidance for WOLF's system prompt (how to use this component)
  context()        a snapshot of data WOLF should see at the start of a conversation
  on_end(agent)    a hook when a conversation ends (memory uses it to reflect and journal)

Where components come from (first match wins):
  1. built-ins:            "memory", "web_search", "clock", "reminders"; off by default:
                           "calendar" (turns on when you connect one), "research"
  2. your plugin folder:   $WOLF_HOME/components/<name>.py  (any Component subclass inside)
  3. installed packages:   entry point group "wolf.components"
  4. an import path:       "package.module:ClassName"

Which ones run is set in $WOLF_HOME/config.json ("components": [...]) or with
`wolf components enable/disable NAME`. Without a setting, DEFAULT_COMPONENTS run.
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect
from dataclasses import dataclass, field
from importlib.metadata import entry_points
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..loop import ToolError, validate
from ..memory import MemoryStore

if TYPE_CHECKING:
    from ..loop import AgentLoop

BUILTINS: dict[str, str] = {
    "memory": "wolf.components.memory:MemoryComponent",
    "web_search": "wolf.components.web:WebSearchComponent",
    "clock": "wolf.components.clock:ClockComponent",
    "research": "wolf.components.research:ResearchComponent",
    "calendar": "wolf.components.calendar:CalendarComponent",
    "reminders": "wolf.components.reminders:RemindersComponent",
}
DEFAULT_COMPONENTS = ["memory", "web_search", "clock", "reminders"]
ENTRY_POINT_GROUP = "wolf.components"


@dataclass
class ComponentContext:
    """What a component gets when it is created."""
    store: MemoryStore
    config: dict[str, Any] = field(default_factory=dict)

    @property
    def home(self) -> Path:
        return self.store.home

    def settings(self, component: str) -> dict[str, Any]:
        """Per-component settings from config.json: {"settings": {"<name>": {...}}}."""
        return dict((self.config.get("settings") or {}).get(component) or {})


class Component:
    """Base class for WOLF components. Override only what you need."""

    name = "component"
    description = ""

    def __init__(self, ctx: ComponentContext):
        self.ctx = ctx

    def tools(self) -> list[dict[str, Any]]:
        return []

    def call(self, name: str, args: dict[str, Any]) -> str:
        raise ToolError(f"{self.name} has no tool named {name}")

    def server_tools(self) -> list[dict[str, Any]]:
        return []

    def instructions(self) -> str:
        return ""

    def context(self) -> str:
        return ""

    def on_end(self, agent: AgentLoop) -> str | None:
        return None


class ComponentError(Exception):
    pass


class Toolkit:
    """Combines components into the single toolbox the agent loop talks to."""

    def __init__(self, components: list[Component]):
        self.components = list(components)
        self._defs: list[dict[str, Any]] = []
        self._owner: dict[str, tuple[Component, dict[str, Any]]] = {}
        for comp in self.components:
            for spec in comp.tools():
                if spec["name"] in self._owner:
                    other = self._owner[spec["name"]][0].name
                    raise ComponentError(f"Components '{other}' and '{comp.name}' both define a tool "
                                         f"named '{spec['name']}'. Disable one of them.")
                self._owner[spec["name"]] = (comp, spec)
                self._defs.append(spec)  # frozen at start so the prompt cache stays valid

    def definitions(self) -> list[dict[str, Any]]:
        return self._defs

    def call(self, name: str, args: dict[str, Any]) -> str:
        if name not in self._owner:
            raise ToolError(f"Unknown tool: {name}")
        comp, spec = self._owner[name]
        validate(spec, args)
        return comp.call(name, args)

    def server_tools(self) -> list[dict[str, Any]]:
        return [t for c in self.components for t in c.server_tools()]

    def instructions(self) -> str:
        parts = [(c.name, c.instructions().strip()) for c in self.components]
        return "\n\n".join(f"## {name}\n{text}" for name, text in parts if text)

    def context(self) -> str:
        return "\n\n".join(t for t in (c.context().strip() for c in self.components) if t)

    def get(self, name: str) -> Component | None:
        return next((c for c in self.components if c.name == name), None)


# ---------------------------------------------------------------- discovery

def plugin_dir(home: Path) -> Path:
    return home / "components"


def _load_target(target: str) -> type[Component]:
    module_name, _, attr = target.partition(":")
    module = importlib.import_module(module_name)
    cls = getattr(module, attr, None) if attr else None
    if not (inspect.isclass(cls) and issubclass(cls, Component)):
        raise ComponentError(f"{target} is not a WOLF Component class")
    return cls


def _load_plugin_file(path: Path) -> type[Component]:
    spec = importlib.util.spec_from_file_location(f"wolf_plugin_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise ComponentError(f"Can't load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    found = [obj for obj in vars(module).values()
             if inspect.isclass(obj) and issubclass(obj, Component) and obj is not Component
             and obj.__module__ == module.__name__]
    if len(found) != 1:
        raise ComponentError(f"{path.name} must define exactly one Component subclass (found {len(found)})")
    return found[0]


def _entry_points() -> dict[str, Any]:
    try:
        return {ep.name: ep for ep in entry_points(group=ENTRY_POINT_GROUP)}
    except Exception:
        return {}


def resolve(name: str, home: Path) -> type[Component]:
    """Find the component class for a name (see the module docstring for the search order)."""
    if name in BUILTINS:
        return _load_target(BUILTINS[name])
    plugin = plugin_dir(home) / f"{name}.py"
    if plugin.is_file():
        return _load_plugin_file(plugin)
    eps = _entry_points()
    if name in eps:
        cls = eps[name].load()
        if not (inspect.isclass(cls) and issubclass(cls, Component)):
            raise ComponentError(f"Entry point {name} is not a WOLF Component class")
        return cls
    if ":" in name:
        return _load_target(name)
    raise ComponentError(f"No component named '{name}'. Run `wolf components` to see what's available.")


def available(home: Path) -> dict[str, str]:
    """Every component WOLF can find: name -> one-line description."""
    out: dict[str, str] = {}
    names = list(BUILTINS) + sorted(p.stem for p in plugin_dir(home).glob("*.py") if not p.stem.startswith("_"))
    names += sorted(n for n in _entry_points() if n not in names)
    for name in names:
        try:
            out[name] = resolve(name, home).description or ""
        except Exception as e:  # a broken plugin shouldn't hide the others
            out[name] = f"(can't load: {e})"
    return out


def enabled_names(config: dict[str, Any]) -> list[str]:
    names = config.get("components")
    return list(names) if isinstance(names, list) else list(DEFAULT_COMPONENTS)


def load_components(ctx: ComponentContext, names: list[str]) -> list[Component]:
    comps = []
    for name in names:
        comp = resolve(name, ctx.home)(ctx)
        if not comp.name or comp.name == "component":
            comp.name = name.rsplit(":", 1)[-1]
        comps.append(comp)
    return comps
