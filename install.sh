#!/bin/sh
# Add App Cleaner to the app grid, or take it out again with --remove
set -e

APP_ID="dev.local.AppCleaner"
DESKTOP_FILE="$HOME/.local/share/applications/$APP_ID.desktop"
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"
ICON_FILE="$ICON_DIR/$APP_ID.svg"

refresh() {
    update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
    gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
}

if [ "$1" = "--remove" ]; then
    rm -f "$DESKTOP_FILE" "$ICON_FILE"
    refresh
    echo "Removed App Cleaner from the app grid."
    exit 0
fi

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$(dirname "$DESKTOP_FILE")" "$ICON_DIR"
cp "$PROJECT_DIR/data/$APP_ID.svg" "$ICON_FILE"
cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=App Cleaner
Comment=Uninstall apps and remove their leftover files
Exec=python3 -m app_cleaner
Path=$PROJECT_DIR
Icon=$APP_ID
Terminal=false
Categories=Utility;
StartupNotify=true
StartupWMClass=$APP_ID
EOF
refresh
echo "App Cleaner added to the app grid."
