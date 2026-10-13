#!/usr/bin/env bash
# Packs the desktop helper as desktop-helper/dist/MyAgentCrewDesktop.app, signed ad hoc.
# It installs nothing by default. With --install it also copies the app to ~/Applications and
# writes the LaunchAgent file, then prints the launchctl line that loads it; it loads nothing.
#
# Every rebuild changes the signature, and macOS then forgets the helper's Screen Recording and
# Accessibility grants: they have to be given again in System Settings.
set -euo pipefail

name="MyAgentCrewDesktop"
bundle_id="com.my-agent-crew.desktop"

install=0
for argument in "$@"; do
    case "$argument" in
        --install) install=1 ;;
        *)
            printf '%s\n' "usage: desktop-helper-pack.sh [--install]" >&2
            exit 64
            ;;
    esac
done

xml_escape() {
    printf '%s' "$1" | sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g'
}

package="$(dirname "$0")/../desktop-helper"
app="$package/dist/$name.app"

swift build --package-path "$package" --configuration release
binary="$(swift build --package-path "$package" --configuration release --show-bin-path)/$name"
version="$("$binary" --version)"
case "$version" in
    "" | *[!0-9.]*)
        printf '%s\n' "The helper reports the version '$version', which is not a version." >&2
        exit 1
        ;;
esac

rm -rf "$app"
mkdir -p "$app/Contents/MacOS"
cp "$binary" "$app/Contents/MacOS/$name"
sed "s/__VERSION__/$version/g" "$package/Info.plist" > "$app/Contents/Info.plist"
plutil -lint "$app/Contents/Info.plist" > /dev/null
codesign --force -s - --identifier "$bundle_id" "$app"
codesign --verify --strict "$app"
printf '%s\n' "Packed $app (version $version, signed ad hoc)."

if [ "$install" -eq 0 ]; then
    exit 0
fi

installed="$HOME/Applications/$name.app"
agents="$HOME/Library/LaunchAgents"
plist="$agents/$bundle_id.plist"
socket="$HOME/.my-agent-crew/desktop/sock"
log="$HOME/Library/Logs/$bundle_id.log"

mkdir -p "$HOME/Applications" "$agents" "$HOME/Library/Logs"
rm -rf "$installed"
ditto "$app" "$installed"
codesign --verify --strict "$installed"

# Started again only after a crash: a helper that ends by itself (its folder is open to others,
# another helper already answers on the socket) said why in the log, and would end the same way
# every ten seconds. It runs in the owner's graphical session only; nowhere else is there a screen.
cat > "$plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$bundle_id</string>
    <key>ProgramArguments</key>
    <array>
        <string>$(xml_escape "$installed/Contents/MacOS/$name")</string>
        <string>--socket</string>
        <string>$(xml_escape "$socket")</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <dict>
        <key>Crashed</key>
        <true/>
    </dict>
    <key>LimitLoadToSessionType</key>
    <string>Aqua</string>
    <key>StandardErrorPath</key>
    <string>$(xml_escape "$log")</string>
</dict>
</plist>
PLIST
plutil -lint "$plist" > /dev/null

printf '%s\n' "Installed $installed and wrote $plist; the helper's own words go to $log."
printf '%s\n' "Nothing was loaded. To load it:"
printf '%s\n' "  launchctl bootstrap gui/$(id -u) $plist"
