import threading
from pathlib import Path

from gi.repository import Adw, Gio, GLib, Gtk

from . import core

SOURCE_LABELS = {
    "apt": "Installed with apt",
    "snap": "Installed as a Snap",
    "flatpak": "Installed as a Flatpak",
    "none": "Not installed through a package manager",
}


def run_in_thread(work, done):
    """Run work() on a worker thread, then done(result, error) on the main thread."""
    def target():
        try:
            result, error = work(), None
        except Exception as e:
            result, error = None, e
        GLib.idle_add(lambda: done(result, error) and False)
    threading.Thread(target=target, daemon=True).start()


def short_path(path):
    path = str(path)
    home = str(core.HOME)
    return "~" + path[len(home):] if path.startswith(home + "/") else path


class AppCleanerWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(title="App Cleaner", default_width=560, default_height=640, **kwargs)
        self.app = None
        self.checks = []  # (Leftover, Gtk.CheckButton)

        self.toasts = Adw.ToastOverlay()
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        toolbar = Adw.ToolbarView(content=self.stack)
        toolbar.add_top_bar(Adw.HeaderBar())
        self.toasts.set_child(toolbar)
        self.set_content(self.toasts)

        self.stack.add_named(self._build_start_page(), "start")
        self.stack.add_named(self._build_busy_page(), "busy")
        self.results_holder = Adw.Bin()
        self.stack.add_named(self.results_holder, "results")
        self.done_page = Adw.StatusPage(icon_name="object-select-symbolic")
        again = Gtk.Button(label="Clean Another App", halign=Gtk.Align.CENTER, css_classes=["pill", "suggested-action"])
        again.connect("clicked", lambda *_: self.show_start())
        self.done_page.set_child(again)
        self.stack.add_named(self.done_page, "done")

    # Pages

    def _build_start_page(self):
        page = Adw.StatusPage(
            icon_name="user-trash-symbolic",
            title="Remove an App",
            description="Choose an app to uninstall it and clean up the files it leaves behind.",
        )
        browse = Gtk.Button(label="Browse Installed Apps", halign=Gtk.Align.CENTER, css_classes=["pill", "suggested-action"])
        browse.connect("clicked", lambda *_: self._open_app_picker())
        page.set_child(browse)
        return page

    def _build_busy_page(self):
        self.busy_page = Adw.StatusPage(paintable=Adw.SpinnerPaintable.new(None))
        self.busy_page.get_paintable().set_widget(self.busy_page)
        return self.busy_page

    def _build_results_page(self, leftovers, preview):
        app = self.app
        self.checks = []

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24, margin_top=24, margin_bottom=24,
                      margin_start=16, margin_end=16)

        header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        icon = Gtk.Image(pixel_size=96, css_classes=["icon-dropshadow"])
        if app.icon:
            icon.set_from_gicon(app.icon)
        else:
            icon.set_from_icon_name("application-x-executable")
        header.append(icon)
        header.append(Gtk.Label(label=app.name, css_classes=["title-1"], wrap=True))
        source = SOURCE_LABELS[app.source] + (f": {app.package}" if app.package else "")
        header.append(Gtk.Label(label=source, css_classes=["dim-label"], wrap=True))
        box.append(header)

        if preview.blocked:
            box.append(self._banner(f"This app can't be removed safely. {preview.blocked}", "error"))
        elif len(preview.packages) > 1:
            others = ", ".join(p for p in preview.packages if p != app.package)
            box.append(self._banner(f"Uninstalling will also remove these packages: {others}", "warning"))
        elif app.source == "none":
            box.append(self._banner("This app wasn't installed through a package manager, so only the "
                                    "files listed below will be removed.", "dim-label"))

        group = Adw.PreferencesGroup(title="Leftover Files")
        self.total_label = Gtk.Label(css_classes=["dim-label", "numeric"], valign=Gtk.Align.END)
        if leftovers:
            group.set_header_suffix(self.total_label)
            if any(not l.exact for l in leftovers):
                group.set_description("Unticked items only partly match the app's name. "
                                      "Check them before ticking.")
            for leftover in leftovers:
                check = Gtk.CheckButton(active=leftover.exact, valign=Gtk.Align.CENTER)
                check.connect("toggled", lambda *_: self._update_remove_button())
                row = Adw.ActionRow(title=GLib.markup_escape_text(short_path(leftover.path)),
                                    subtitle=GLib.format_size(leftover.size), activatable_widget=check)
                row.add_prefix(check)
                group.add(row)
                self.checks.append((leftover, check))
        else:
            group.add(Adw.ActionRow(title="No leftover files found"))
        box.append(group)

        buttons = Gtk.Box(spacing=12, halign=Gtk.Align.CENTER)
        cancel = Gtk.Button(label="Cancel", css_classes=["pill"])
        cancel.connect("clicked", lambda *_: self.show_start())
        self.remove_button = Gtk.Button(css_classes=["pill", "destructive-action"], sensitive=not preview.blocked)
        self.remove_button.connect("clicked", lambda *_: self._confirm_removal())
        buttons.append(cancel)
        buttons.append(self.remove_button)
        box.append(buttons)
        self.blocked = bool(preview.blocked)
        self._update_remove_button()

        clamp = Adw.Clamp(maximum_size=600, child=box)
        return Gtk.ScrolledWindow(child=clamp, hscrollbar_policy=Gtk.PolicyType.NEVER)

    def _banner(self, text, css_class):
        return Gtk.Label(label=text, wrap=True, justify=Gtk.Justification.CENTER, css_classes=[css_class])

    # Flow

    def show_start(self):
        self.stack.set_visible_child_name("start")

    def show_busy(self, title):
        self.busy_page.set_title(title)
        self.stack.set_visible_child_name("busy")

    def load(self, desktop):
        self.show_busy("Looking for Leftovers…")

        def work():
            app = core.load_app(desktop)
            return app, core.find_leftovers(app), core.removal_preview(app)

        run_in_thread(work, self._on_loaded)

    def _on_loaded(self, result, error):
        if error:
            self.show_start()
            self.toasts.add_toast(Adw.Toast(title=str(error)))
            return
        self.app, leftovers, preview = result
        self.results_holder.set_child(self._build_results_page(leftovers, preview))
        self.stack.set_visible_child_name("results")

    def _selected(self):
        return [leftover for leftover, check in self.checks if check.get_active()]

    def _update_remove_button(self):
        selected = self._selected()
        count = len(selected)
        self.total_label.set_label(f"{GLib.format_size(sum(l.size for l in selected))} selected")
        if self.app.package:
            label = "Uninstall" + (f" and Trash {count} Item{'s' if count != 1 else ''}" if count else "")
            self.remove_button.set_sensitive(not self.blocked)
        else:
            label = f"Move {count} Item{'s' if count != 1 else ''} to Trash"
            self.remove_button.set_sensitive(count > 0)
        self.remove_button.set_label(label)

    def _confirm_removal(self):
        app, selected = self.app, self._selected()
        parts = []
        if app.package:
            parts.append(f"The {app.package} package will be uninstalled"
                         + (" (you'll be asked for your password)" if app.source == "apt" else "") + ".")
        if selected:
            size = GLib.format_size(sum(l.size for l in selected))
            parts.append(f"{len(selected)} item{'s' if len(selected) != 1 else ''} ({size}) will be moved "
                         "to the Trash, where you can restore them if needed.")
        dialog = Adw.AlertDialog(heading=f"Remove {app.name}?", body="\n\n".join(parts))
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("remove", "Remove")
        dialog.set_response_appearance("remove", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_close_response("cancel")
        dialog.connect("response", lambda _d, response: response == "remove" and self._remove(selected))
        dialog.present(self)

    def _remove(self, selected):
        app = self.app
        self.show_busy(f"Removing {app.name}…")

        def work():
            ok, message = core.uninstall(app)
            if not ok:
                return False, message, []
            return True, "", core.move_to_trash(l.path for l in selected)

        run_in_thread(work, lambda result, error: self._on_removed(selected, result, error))

    def _on_removed(self, selected, result, error):
        if error or not result[0]:
            self.stack.set_visible_child_name("results")
            self.toasts.add_toast(Adw.Toast(title=str(error) if error else result[1], timeout=8))
            return
        failures = result[2]
        trashed = len(selected) - len(failures)
        self.done_page.set_title(f"{self.app.name} Was Removed")
        description = f"{trashed} item{'s' if trashed != 1 else ''} moved to the Trash." if selected else ""
        if failures:
            names = "\n".join(GLib.markup_escape_text(short_path(p)) for p, _ in failures)
            description += f"\n\nThese couldn't be moved to the Trash:\n{names}"
        self.done_page.set_description(description)
        self.stack.set_visible_child_name("done")

    # App picker

    def _open_app_picker(self):
        apps = sorted(
            (info for info in Gio.AppInfo.get_all()
             if isinstance(info, Gio.DesktopAppInfo) and info.should_show() and info.get_filename()),
            key=lambda info: info.get_name().lower(),
        )

        listbox = Gtk.ListBox(css_classes=["boxed-list"], selection_mode=Gtk.SelectionMode.NONE,
                              margin_top=12, margin_bottom=12, margin_start=12, margin_end=12,
                              valign=Gtk.Align.START)
        for info in apps:
            row = Adw.ActionRow(title=GLib.markup_escape_text(info.get_name()), activatable=True)
            icon = Gtk.Image(pixel_size=32)
            if info.get_icon():
                icon.set_from_gicon(info.get_icon())
            row.add_prefix(icon)
            row.filename = info.get_filename()
            row.search_text = info.get_name().lower()
            listbox.append(row)

        search = Gtk.SearchEntry(placeholder_text="Search apps", hexpand=True)
        listbox.set_filter_func(lambda row: search.get_text().lower() in row.search_text)
        search.connect("search-changed", lambda *_: listbox.invalidate_filter())

        toolbar = Adw.ToolbarView(content=Gtk.ScrolledWindow(child=listbox, vexpand=True))
        toolbar.add_top_bar(Adw.HeaderBar())
        search_bar = Gtk.Box(margin_start=12, margin_end=12, margin_bottom=6)
        search_bar.append(search)
        toolbar.add_top_bar(search_bar)

        dialog = Adw.Dialog(title="Choose an App", content_width=420, content_height=560, child=toolbar)

        def on_activated(_listbox, row):
            dialog.close()
            self.load(Path(row.filename))

        listbox.connect("row-activated", on_activated)
        search.connect("activate", lambda *_: (row := self._first_visible(listbox)) and on_activated(listbox, row))
        dialog.present(self)
        search.grab_focus()

    def _first_visible(self, listbox):
        row = listbox.get_first_child()
        while row and not row.get_child_visible():
            row = row.get_next_sibling()
        return row
