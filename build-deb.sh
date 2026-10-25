#!/bin/sh
# Build a .deb package of App Cleaner into dist/
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_ID="dev.local.AppCleaner"
VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$PROJECT_DIR/app_cleaner/__init__.py")"
PKG="$PROJECT_DIR/build/app-cleaner"
DEB="$PROJECT_DIR/dist/app-cleaner_${VERSION}_all.deb"

rm -rf "$PKG"
mkdir -p "$PKG/DEBIAN" "$PKG/usr/bin" "$PKG/usr/lib/app-cleaner" \
    "$PKG/usr/share/applications" "$PKG/usr/share/icons/hicolor/scalable/apps" \
    "$PKG/usr/share/doc/app-cleaner" "$PROJECT_DIR/dist"

# The program itself, without compiled caches
cp -r "$PROJECT_DIR/app_cleaner" "$PKG/usr/lib/app-cleaner/"
find "$PKG" -name __pycache__ -prune -exec rm -rf {} +

cat > "$PKG/usr/bin/app-cleaner" <<'EOF'
#!/bin/sh
PYTHONPATH=/usr/lib/app-cleaner exec python3 -m app_cleaner "$@"
EOF

cat > "$PKG/usr/share/applications/$APP_ID.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=App Cleaner
Comment=Uninstall apps and remove their leftover files
Exec=app-cleaner
Icon=$APP_ID
Terminal=false
Categories=Utility;
Keywords=uninstall;remove;leftovers;cleanup;
StartupNotify=true
StartupWMClass=$APP_ID
EOF

cp "$PROJECT_DIR/data/$APP_ID.svg" "$PKG/usr/share/icons/hicolor/scalable/apps/"
cp "$PROJECT_DIR/LICENSE" "$PKG/usr/share/doc/app-cleaner/copyright"

cat > "$PKG/DEBIAN/control" <<EOF
Package: app-cleaner
Version: $VERSION
Architecture: all
Maintainer: Ivo Tsochev <ivo.tsochev@gmail.com>
Depends: python3 (>= 3.9), python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1 (>= 1.6), pkexec | policykit-1
Section: utils
Priority: optional
Installed-Size: $(du -sk "$PKG/usr" | cut -f1)
Description: Uninstall apps and remove their leftover files
 An AppCleaner-style uninstaller for Ubuntu. Pick an app, review the
 leftover files it left in your home folder, and remove the app along
 with them. Works with apt, Snap and Flatpak apps. Files are moved to
 the Trash, so they can be restored.
EOF

find "$PKG" -type d -exec chmod 755 {} +
find "$PKG" -type f -exec chmod 644 {} +
chmod 755 "$PKG/usr/bin/app-cleaner"

dpkg-deb --root-owner-group --build "$PKG" "$DEB"
echo "Built $DEB"
