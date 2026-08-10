# ───────────────────────────────────────────────────────────────────
# plugin_loader.py, discovers third-party ActionPlugin subclasses
# ───────────────────────────────────────────────────────────────────
# Scans a directory (by default desktop/plugins/) for *.py files and
# loads any ActionPlugin subclass it finds into a registry action_
# router.py can dispatch through, exactly like the built-in plugins
# in plugins_builtin.py.
#
# "NEVER BLOCK STARTUP", SAME PHILOSOPHY AS routines.py
# ---------------------------------------------------------
# routines.py's load_routines() treats a missing/malformed
# routines.yaml as "load nothing, log it, keep going" rather than
# raising, a personal macro file someone hand-edited shouldn't be
# able to crash the whole assistant on startup. Third-party plugins
# are the same kind of user-supplied, not-necessarily-well-formed
# input, just as Python files instead of YAML: a plugin file that
# fails to import, defines a class with a blank action_name, doesn't
# implement execute() (so it can't even be instantiated, since
# ActionPlugin.execute is an abstractmethod), or collides with an
# already-registered action name is logged and SKIPPED, never
# raised. One broken plugin can't take down the other plugins, let
# alone the app.
# ───────────────────────────────────────────────────────────────────

import importlib.util
import inspect
import os

from .plugin_base import ActionPlugin


def _load_module_from_path(path):
    """Import the .py file at `path` as its own module, independent
    of any package layout, this is what lets desktop/plugins/ hold
    arbitrary user files without them needing to be a proper Python
    package."""
    module_name = "_makeitso_plugin__" + os.path.splitext(os.path.basename(path))[0]
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not build an import spec for {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _plugin_classes_defined_in(module):
    """Return every ActionPlugin subclass DEFINED in `module` itself
    (not merely imported into it, e.g. `from core.plugin_base import
    ActionPlugin` shouldn't cause ActionPlugin to be picked up as a
    plugin, and a plugin file that imports another plugin file's class
    for reuse shouldn't double-register it)."""
    found = []
    for _, obj in inspect.getmembers(module, inspect.isclass):
        if obj is ActionPlugin:
            continue
        if not issubclass(obj, ActionPlugin):
            continue
        if obj.__module__ != module.__name__:
            continue
        found.append(obj)
    return found


def _try_register(plugin_class, filename, taken_names, out):
    """Instantiate and validate one plugin class, adding it to `out`
    on success. Any failure along the way is logged and swallowed,
    see the module docstring above for why."""
    try:
        instance = plugin_class()
    except Exception as e:
        # Most commonly TypeError: Python refuses to instantiate an
        # ABC subclass that never overrode the abstractmethod
        # execute(), that's exactly the "malformed plugin" case this
        # function needs to survive.
        print(f"  [plugins] Skipping {plugin_class.__name__} in {filename}: "
              f"could not instantiate it ({type(e).__name__}: {e})")
        return

    action_name = getattr(instance, "action_name", "")
    if not isinstance(action_name, str) or not action_name.strip():
        print(f"  [plugins] Skipping {plugin_class.__name__} in {filename}: "
              f"missing/blank action_name")
        return
    action_name = action_name.strip()

    if not callable(getattr(instance, "execute", None)):
        print(f"  [plugins] Skipping {plugin_class.__name__} in {filename}: "
              f"no callable execute()")
        return

    if action_name in taken_names:
        print(f"  [plugins] Skipping {plugin_class.__name__} in {filename}: "
              f"action name \"{action_name}\" is already registered "
              f"(built-in actions can't be overridden; the first "
              f"plugin to claim a name wins)")
        return

    out[action_name] = instance
    print(f"  [plugins] Loaded plugin \"{action_name}\" from {filename} "
          f"({plugin_class.__name__})")


def discover_plugins(plugins_dir, existing_action_names=None):
    """
    Scan `plugins_dir` for third-party ActionPlugin subclasses.

    Only *.py files directly inside `plugins_dir` are scanned, NOT
    subdirectories. That's deliberate: desktop/plugins/examples/
    ships a documented template plugin that should be copied up into
    desktop/plugins/ to activate it, not auto-loaded from where it
    sits. Files starting with "_" (e.g. a private helper module, or
    __init__.py) are skipped too.

    PARAMETERS
    ----------
    plugins_dir : str
        Directory to scan. A missing directory is not an error, it
        just means no third-party plugins are installed.
    existing_action_names : iterable of str, optional
        Action names already claimed (by built-in plugins). A
        discovered plugin trying to reuse one of these is skipped so
        a third-party plugin can never shadow/override a built-in
        action.

    RETURNS
    -------
    dict
        {action_name: plugin_instance} for every plugin that loaded
        and validated successfully. Never raises.
    """
    taken = set(existing_action_names or ())
    discovered = {}

    if not plugins_dir or not os.path.isdir(plugins_dir):
        return discovered

    try:
        filenames = sorted(os.listdir(plugins_dir))
    except OSError as e:
        print(f"  [plugins] Could not list {plugins_dir}: {e}")
        return discovered

    for filename in filenames:
        if not filename.endswith(".py") or filename.startswith("_"):
            continue
        path = os.path.join(plugins_dir, filename)
        if not os.path.isfile(path):
            continue

        try:
            module = _load_module_from_path(path)
            plugin_classes = _plugin_classes_defined_in(module)
        except Exception as e:
            print(f"  [plugins] Skipping {filename}: failed to import "
                  f"({type(e).__name__}: {e})")
            continue

        if not plugin_classes:
            print(f"  [plugins] Skipping {filename}: no ActionPlugin "
                  f"subclass found in it")
            continue

        for plugin_class in plugin_classes:
            _try_register(plugin_class, filename, taken | discovered.keys(), discovered)

    if discovered:
        print(f"  [plugins] Loaded {len(discovered)} third-party plugin(s) "
              f"from {plugins_dir}")

    return discovered


def build_registry(builtin_plugins, plugins_dir):
    """
    Build the full {action_name: plugin_instance} registry: every
    built-in plugin, plus every third-party plugin discovered in
    `plugins_dir` that doesn't collide with a built-in name.

    PARAMETERS
    ----------
    builtin_plugins : list of ActionPlugin
        Already-instantiated built-in plugins (see plugins_builtin.
        BUILTIN_PLUGINS).
    plugins_dir : str
        Directory to scan for third-party plugins.

    RETURNS
    -------
    dict
        {action_name: plugin_instance}.
    """
    registry = {}
    for plugin in builtin_plugins:
        action_name = (plugin.action_name or "").strip()
        if not action_name:
            # A built-in with a blank action_name is a programmer
            # error in THIS codebase, not user input, fail loudly
            # rather than silently dropping a built-in action.
            raise ValueError(
                f"Built-in plugin {plugin.__class__.__name__} has no action_name"
            )
        registry[action_name] = plugin

    registry.update(discover_plugins(plugins_dir, existing_action_names=registry.keys()))
    return registry
