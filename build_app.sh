#!/bin/bash
# Builds "Ebook Converter.app" with PyInstaller into dist.noindex/.
# Pass --install to also copy it into /Applications.
#
# The output folder is named ".noindex" deliberately. It lives under
# ~/Documents, which Spotlight indexes, and a built .app sitting there shows up
# as a second "Ebook Converter" next to the installed one — re-registered on
# every build, because each rebuild re-signs the bundle with a new ad-hoc
# identity. Spotlight skips any directory whose name ends in .noindex.
set -euo pipefail
cd "$(dirname "$0")"

APP_NAME="Ebook Converter"
BUNDLE_ID="com.netrunner3000.ebookconverter"
DIST="dist.noindex"

source .venv/bin/activate
uv pip install -q pyinstaller

# Regenerate the icon so the bundle never ships a stale one.
python assets/make_icon.py

rm -rf build dist "$DIST"

# Calibre is not bundled — the app shells out to whatever ebook-convert is
# installed. That keeps the bundle at PySide6 size instead of adding Calibre's
# several hundred MB, and means Calibre updates apply without a rebuild.
pyinstaller --noconfirm --clean --windowed \
  --name "$APP_NAME" \
  --icon assets/icon.icns \
  --osx-bundle-identifier "$BUNDLE_ID" \
  --distpath "$DIST" \
  --add-data "assets/icon.icns:assets" \
  --exclude-module PySide6.QtWebEngineCore \
  --exclude-module PySide6.QtWebEngineWidgets \
  --exclude-module PySide6.Qt3DCore \
  --exclude-module PySide6.QtCharts \
  --exclude-module PySide6.QtDataVisualization \
  --exclude-module PySide6.QtMultimedia \
  --exclude-module PySide6.QtQuick3D \
  --exclude-module tkinter \
  main.py

APP="$DIST/$APP_NAME.app"

# The packaged binary is the only thing worth self-testing: a bare PATH and
# PyInstaller's rewritten linker environment are failures that cannot happen
# from source. Run it before the app is trusted with a library of books.
echo
echo "Running self-test against the built binary…"
"$APP/Contents/MacOS/$APP_NAME" --selftest

echo
echo "Built: $APP ($(du -sh "$APP" | cut -f1))"

if [[ "${1:-}" == "--install" ]]; then
  rm -rf "/Applications/$APP_NAME.app"
  cp -R "$APP" /Applications/
  touch "/Applications/$APP_NAME.app"  # nudge Finder/Dock to refresh the cached icon
  echo "Installed: /Applications/$APP_NAME.app"

  # Nothing left behind to be indexed or backed up.
  rm -rf build "$DIST"
  echo "Cleaned: build/ and $DIST/"
else
  echo "Run '$0 --install' to copy it into /Applications."
  echo "$DIST/ is skipped by Spotlight; --install removes it entirely."
fi
