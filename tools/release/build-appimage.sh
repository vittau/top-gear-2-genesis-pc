#!/usr/bin/env bash
# Build the single-file Linux AppImage from a staged release payload.
#
# Usage: build-appimage.sh --payload DIR --out DIR [--version V]
#                          [--tools DIR] [--binary TG2Recomp]
#
# The payload is the folder build-linux.sh produced (TG2Recomp, assets/,
# licenses/, README.txt, BUILD-INFO.txt). SDL2 is already linked statically,
# so the AppImage adds only the runtime and desktop metadata; it does not
# bundle host libraries and therefore keeps the same glibc <= 2.35 floor as
# the tarball. Run it on the oldest glibc you support (CI uses ubuntu-22.04).
set -euo pipefail
repo=$(cd "$(dirname "$0")/../.." && pwd)
payload=""
out="$repo/build-release/dist/linux"
tools="$repo/build-release/appimage-tools"
version="0.2.0"
binary="TG2Recomp"
name="TG2Recomp-x86_64.AppImage"
skip_glibc_check=0

while [ $# -gt 0 ]; do
    case "$1" in
        --payload) payload="$2"; shift 2;;
        --out) out="$2"; shift 2;;
        --tools) tools="$2"; shift 2;;
        --version) version="$2"; shift 2;;
        --binary) binary="$2"; shift 2;;
        --skip-glibc-check) skip_glibc_check=1; shift;;
        -h|--help) sed -n '2,12p' "$0"; exit 0;;
        *) echo "Unknown argument: $1" >&2; exit 2;;
    esac
done
[ -n "$payload" ] || { echo "--payload is required" >&2; exit 2; }
[ -x "$payload/$binary" ] || { echo "payload has no executable: $payload/$binary" >&2; exit 2; }
[ -d "$payload/assets" ] || { echo "payload has no assets directory" >&2; exit 2; }
[ -f "$payload/README.txt" ] || { echo "payload has no README.txt" >&2; exit 2; }
[ "$(uname -m)" = x86_64 ] || { echo "AppImage build requires x86_64" >&2; exit 2; }

mkdir -p "$out" "$tools"

# Pinned tools, SHA-256 verified. Reusing appimagetool's embedded runtime
# avoids its floating "continuous" runtime download.
APPIMAGETOOL="$tools/appimagetool-x86_64.AppImage"
RUNTIME="$tools/runtime-x86_64"
fetch() {
    local url="$1" sha="$2" dest="$3"
    if [ ! -f "$dest" ] || [ "$(sha256sum "$dest" | cut -d' ' -f1)" != "$sha" ]; then
        curl -fL --retry 3 "$url" -o "$dest.tmp"
        printf '%s  %s\n' "$sha" "$dest.tmp" | sha256sum -c -
        mv "$dest.tmp" "$dest"
    fi
    chmod +x "$dest"
}
fetch https://github.com/AppImage/appimagetool/releases/download/1.9.1/appimagetool-x86_64.AppImage \
    ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0 "$APPIMAGETOOL"
if [ ! -s "$RUNTIME" ]; then
    offset=$("$APPIMAGETOOL" --appimage-offset)
    [[ "$offset" =~ ^[1-9][0-9]*$ ]] || { echo "appimagetool runtime offset unavailable" >&2; exit 1; }
    head -c "$offset" "$APPIMAGETOOL" > "$RUNTIME"
fi

work=$(mktemp -d)
trap 'chmod -R u+w "$work" 2>/dev/null; rm -rf "$work"' EXIT
appdir="$work/AppDir"
mkdir -p "$appdir/usr/bin"
cp -a "$payload/." "$appdir/usr/bin/"

cp "$repo/tools/release/AppRun" "$appdir/AppRun"
chmod +x "$appdir/AppRun"
cp "$repo/tools/release/tg2recomp.png" "$appdir/tg2recomp.png"
cp "$repo/tools/release/tg2recomp.png" "$appdir/.DirIcon"
cat > "$appdir/tg2recomp.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Top Gear 2 Recomp
Comment=Native recompilation of Top Gear 2 (USA) for Sega Genesis
Exec=$binary
Icon=tg2recomp
StartupWMClass=tg2recomp
Categories=Game;
Terminal=false
X-AppImage-Version=$version
EOF

app="$out/$name"
rm -f "$app" "$app.sha256"
ARCH=x86_64 "$APPIMAGETOOL" --appimage-extract-and-run --no-appstream \
    --runtime-file "$RUNTIME" "$appdir" "$app"
chmod +x "$app"

# Gate the exact file users download: extract it (no FUSE needed) and run the
# same checks as the tarball, including the glibc symbol floor.
check="$work/extracted"
mkdir -p "$check"
(cd "$check" && "$app" --appimage-extract >/dev/null)
python3 "$repo/tools/release/verify_artifact.py" --dir "$check/squashfs-root" \
    --require "usr/bin/$binary" --require usr/bin/assets --require usr/bin/licenses \
    --require usr/bin/README.txt
if [ "$skip_glibc_check" = 1 ]; then
    echo "build-appimage: glibc check skipped (local development build)"
else
    python3 "$repo/tools/release/verify_glibc.py" \
        --binary "$check/squashfs-root/usr/bin/$binary" --max 2.35
fi

(cd "$out" && sha256sum "$name" > "$name.sha256")
echo "Built $app"
cat "$app.sha256"
