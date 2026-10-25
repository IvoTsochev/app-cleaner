import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw

from .window import AppCleanerWindow

APP_ID = "dev.local.AppCleaner"


def main():
    app = Adw.Application(application_id=APP_ID)
    app.connect("activate", lambda app: (app.get_active_window() or AppCleanerWindow(application=app)).present())
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
