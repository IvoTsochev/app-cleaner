"""Work out where an app came from, find its leftover files, and remove it.

Nothing in this module touches the GUI, so it can be used from a worker thread.
"""

import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from gi.repository import Gio

HOME = Path.home()

# Folders (one level deep) where apps keep per-user config, data and caches
SEARCH_ROOTS = [
    HOME / ".config",
    HOME / ".local" / "share",
    HOME / ".local" / "state",
    HOME / ".cache",
    HOME / ".local" / "share" / "applications",
    HOME / ".config" / "autostart",
]

# Your own folders, where apps sometimes create a folder of their own
USER_FOLDERS = [HOME / "Documents"]

# Names too generic to match on: they'd pull in folders belonging to other apps
GENERIC_NAMES = {
    "app", "apps", "application", "applications", "bin", "cache", "com", "config",
    "data", "desktop", "dev", "env", "files", "flatpak", "gnome", "gtk", "io",
    "kde", "local", "net", "org", "python", "python3", "settings", "sh", "bash",
    "share", "snap", "state", "system", "terminal", "ubuntu", "user", "usr",
}

# Uninstalls that would take any of these with them would break the desktop
DESKTOP_PACKAGES = ("ubuntu-desktop", "ubuntu-session", "gnome-shell", "gdm3")

# Never offer to remove these, whatever they're called
PROTECTED = {HOME, *SEARCH_ROOTS, *USER_FOLDERS, HOME / ".local", HOME / "snap", HOME / ".var", HOME / ".var" / "app"}


@dataclass
class App:
    name: str
    desktop_path: Path
    icon: Gio.Icon | None
    source: str  # "apt", "snap", "flatpak" or "none" (not from a package manager)
    package: str | None
    names: set[str] = field(default_factory=set)
    executable: Path | None = None


@dataclass
class Leftover:
    path: Path
    size: int
    exact: bool  # exact name match (ticked by default) vs. a looser partial match


@dataclass
class RemovalPreview:
    packages: list[str]  # every package the uninstall would remove
    blocked: str | None = None  # reason the uninstall must not go ahead


def load_app(desktop_path):
    info = Gio.DesktopAppInfo.new_from_filename(str(desktop_path))
    if info is None:
        raise ValueError(f"{desktop_path.name} isn't a valid app launcher")

    desktop_id = desktop_path.name.removesuffix(".desktop")
    source, package = _detect_source(desktop_path, info)
    exe = _which(info.get_executable()) if info.get_executable() else None

    app = App(
        name=info.get_name() or desktop_id,
        desktop_path=desktop_path,
        icon=info.get_icon(),
        source=source,
        package=package,
        executable=exe,
    )
    app.names = _name_candidates(app, desktop_id, info)
    return app


def find_leftovers(app):
    found = {}

    def add(path, exact):
        path = Path(path)
        if path in PROTECTED or not _is_under_home(path):
            return
        if path in found:
            found[path].exact |= exact
        else:
            found[path] = Leftover(path, 0, exact)

    for root in SEARCH_ROOTS:
        for entry in _list_dir(root):
            match = _match(entry.name, app.names)
            if match is not None:
                add(entry, match)

    # Folders an app made among your own files, e.g. ~/Documents/Vibe. They may hold
    # your work, so they're never ticked by default.
    for root in USER_FOLDERS:
        for entry in _list_dir(root):
            if _match(entry.name, app.names) is not None:
                add(entry, False)

    # Hidden files and folders directly in the home folder, e.g. ~/.warp
    for entry in _list_dir(HOME):
        if entry.name.startswith("."):
            match = _match(entry.name, app.names)
            if match is not None:
                add(entry, match)

    if app.source == "snap" and app.package:
        add(HOME / "snap" / app.package, True)
    elif app.source == "flatpak" and app.package:
        add(HOME / ".var" / "app" / app.package, True)
    elif app.source == "none":
        # Not from a package manager (e.g. an AppImage): the app itself is in the home folder
        if _is_under_home(app.desktop_path):
            add(app.desktop_path, True)
        if app.executable and _is_under_home(app.executable):
            add(app.executable, True)

    leftovers = [l for l in found.values() if l.path.exists() or l.path.is_symlink()]
    for leftover in leftovers:
        leftover.size = disk_usage(leftover.path)
    return sorted(leftovers, key=lambda l: (not l.exact, str(l.path).lower()))


def removal_preview(app):
    if app.source != "apt":
        return RemovalPreview([app.package] if app.package else [])

    result = subprocess.run(
        ["apt-get", "-s", "purge", app.package],
        capture_output=True, text=True, env={**os.environ, "LC_ALL": "C"},
    )
    packages = [line.split()[1] for line in result.stdout.splitlines() if line.startswith(("Purg ", "Remv "))]
    blocked = None
    if result.returncode != 0:
        blocked = (result.stderr.strip() or "apt couldn't plan the removal").splitlines()[-1]
    elif "essential packages will be removed" in result.stdout.lower():
        blocked = "Removing this would remove packages essential to the system."
    elif any(p.startswith(DESKTOP_PACKAGES) for p in packages):
        blocked = "Removing this would also remove parts of the Ubuntu desktop."
    return RemovalPreview(packages, blocked)


def uninstall(app):
    """Uninstall the app's package. Returns (succeeded, message)."""
    commands = {
        "apt": ["pkexec", "env", "DEBIAN_FRONTEND=noninteractive", "apt-get", "purge", "-y", app.package],
        "snap": ["snap", "remove", "--purge", app.package],
        "flatpak": ["flatpak", "uninstall", "-y", "--delete-data", app.package],
    }
    if app.source not in commands:
        return True, ""
    result = subprocess.run(commands[app.source], capture_output=True, text=True)
    if result.returncode in (126, 127) and app.source == "apt":
        return False, "Uninstall cancelled: the password prompt was dismissed."
    if result.returncode != 0:
        return False, (result.stderr or result.stdout).strip() or "Uninstall failed."
    return True, ""


def move_to_trash(paths):
    """Move paths to the Trash. Returns a list of (path, error message) for any that failed."""
    failures = []
    for path in paths:
        try:
            Gio.File.new_for_path(str(path)).trash(None)
        except Exception as e:
            failures.append((path, str(e)))
    return failures


def disk_usage(path):
    try:
        if path.is_symlink() or not path.is_dir():
            return path.lstat().st_size
    except OSError:
        return 0
    total = 0
    for dirpath, _, filenames in os.walk(path):
        for name in filenames:
            try:
                total += os.lstat(os.path.join(dirpath, name)).st_size
            except OSError:
                pass
    return total


def _detect_source(desktop_path, info):
    real = str(desktop_path.resolve())
    if "/snapd/desktop/applications/" in real:
        name = info.get_string("X-SnapInstanceName") or desktop_path.stem.split("_")[0]
        return "snap", name
    if "/flatpak/exports/" in real:
        return "flatpak", desktop_path.name.removesuffix(".desktop")
    for candidate in dict.fromkeys([str(desktop_path), real]):
        result = subprocess.run(["dpkg-query", "-S", candidate], capture_output=True, text=True)
        if result.returncode == 0 and result.stdout:
            # "pkg: /path", "pkg:amd64: /path" or "pkg1, pkg2: /path"
            owner = result.stdout.splitlines()[0].rsplit(": ", 1)[0].split(",")[0].strip()
            return "apt", owner.split(":")[0]
    return "none", None


def _name_candidates(app, desktop_id, info):
    raw = {desktop_id, app.package, app.name, info.get_startup_wm_class()}
    if "." in desktop_id:
        raw.add(desktop_id.rsplit(".", 1)[1])  # dev.warp.Warp -> Warp
    if app.executable:
        raw.add(app.executable.name)
    icon = info.get_string("Icon")
    if icon and "/" not in icon:
        raw.add(icon)
    if app.name:
        raw.add(re.sub(r"\s+", "-", app.name.strip()))  # "Visual Studio Code" -> visual-studio-code
        raw.add(re.sub(r"\s+", "", app.name.strip()))

    names = set()
    for name in raw:
        if not name:
            continue
        name = name.lower().removesuffix(".desktop").removesuffix(".appimage")
        if len(name) >= 3 and name not in GENERIC_NAMES:
            names.add(name)
    return names


def _match(entry_name, names):
    """True for an exact match, False for a partial match, None for no match."""
    name = entry_name.lower().lstrip(".")
    stem = name.rsplit(".", 1)[0] if "." in name else name
    if name in names or stem in names:
        return True
    # Reverse-domain IDs ending in the app's name, e.g. github.com.thewh1teagle.vibe
    for candidate in (name, stem):
        parts = candidate.split(".")
        if len(parts) >= 3 and parts[-1] in names:
            return True
    for candidate in names:
        if len(candidate) >= 4 and any(name.startswith(candidate + sep) for sep in "-_."):
            return False
    return None


def _list_dir(path):
    try:
        return list(path.iterdir())
    except OSError:
        return []


def _is_under_home(path):
    try:
        return Path(os.path.abspath(path)).is_relative_to(HOME) and Path(os.path.abspath(path)) != HOME
    except ValueError:
        return False


def _which(exe):
    if os.path.isabs(exe):
        return Path(exe)
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        candidate = Path(directory) / exe
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None
