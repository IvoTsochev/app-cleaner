<div align="center">

<img src="data/dev.local.AppCleaner.svg" width="128" alt="App Cleaner icon">

# App Cleaner

**Uninstall apps on Ubuntu and clean up the files they leave behind.**

Removing an app usually leaves its settings, caches and data scattered around
your home folder. App Cleaner finds them and removes them together with the app.

<img src="docs/screenshots/1-app-list.png" width="720" alt="Choosing an app to remove">

</div>

## Features

- 📦 **Works with apt, Snap and Flatpak apps.** It detects where each app came from.
- 🔍 **Finds the leftovers** in `~/.config`, `~/.cache`, `~/.local/share` and other places apps store files.
- ✅ **You stay in control.** Every file is listed, and nothing is removed unless it's ticked.
- 🗑️ **Nothing is deleted for good.** Leftover files go to the Trash, so you can restore them.
- 🛡️ **Protects your system.** It won't uninstall anything that would take essential system packages with it.

## Install

> Needs **Ubuntu 25.04 or newer** (or another Debian-based system with libadwaita 1.6+).

1. Download the latest `app-cleaner_x.x.x_all.deb` from the [**Releases**](../../releases/latest) page.
2. Double-click it to open it in App Center and click **Install**, or run this in a terminal:

   ```sh
   sudo apt install ./app-cleaner_*_all.deb
   ```

3. Open **App Cleaner** from your app grid.

To uninstall it later:

```sh
sudo apt remove app-cleaner
```

## How to use it

### 1. Pick an app

Click **Browse Installed Apps**, search for the app, and click it.

### 2. Review what it found

<div align="center">
<img src="docs/screenshots/2-review.png" width="720" alt="Reviewing leftover files">
</div>

- **Ticked** items match the app's name exactly. These are safe to remove.
- **Unticked** items only partly match (e.g. `nautilus-python` for Files). Check them before ticking.
- Anything found in `~/Documents` is always unticked, since it may be your own work.
- The total size of the ticked items is shown above the list.

### 3. Remove

Click **Remove**. The app is uninstalled (apt apps ask for your password), and the
ticked files are moved to the Trash.

<div align="center">
<img src="docs/screenshots/3-done.png" width="720" alt="App removed">
</div>

## Safety

- Before removing an apt package, App Cleaner does a dry run. If other packages would
  be removed too, it shows you which ones. If essential packages or parts of the
  Ubuntu desktop would go, it refuses.
- It only touches the items you ticked, and only inside your home folder.
- Files are moved to the Trash, never deleted outright.

<details>
<summary><b>Where exactly does it look?</b></summary>

`~/.config`, `~/.local/share`, `~/.local/state`, `~/.cache`,
`~/.local/share/applications`, `~/.config/autostart`, hidden items directly in `~`,
plus `~/snap/<name>` for Snaps and `~/.var/app/<id>` for Flatpaks.
Folders named with a reverse-domain ID ending in the app's name
(e.g. `github.com.thewh1teagle.vibe`) count as exact matches.

</details>

## For developers

<details>
<summary><b>Run from source</b></summary>

You need Python 3 with GTK 4 and libadwaita bindings. Ubuntu's desktop includes them
(`python3-gi`, `gir1.2-gtk-4.0`, `gir1.2-adw-1`).

```sh
python3 -m app_cleaner      # run it
./install.sh                # add it to your app grid, running from this folder
./install.sh --remove       # take it out again
```

</details>

<details>
<summary><b>Build the .deb</b></summary>

1. Set the version in `app_cleaner/__init__.py`.
2. Run:

   ```sh
   ./build-deb.sh
   ```

The package is written to `dist/app-cleaner_<version>_all.deb`.

</details>

## License

[MIT](LICENSE)
