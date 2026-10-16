#!/bin/sh
# Safe, configuration-preserving update for an existing os-xray 3.x installation.
# Does not stop Xray/tun2socks, touch config.xml, replace binaries or run Apply.
set -eu

[ "$(id -u)" -eq 0 ] || { echo "ERROR: run as root" >&2; exit 1; }
ROOT=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
SRC="$ROOT/plugin"
VERSION_FILE=/usr/local/opnsense/mvc/app/models/OPNsense/Xray/version.txt
[ -d "$SRC" ] && [ -f "$ROOT/install.sh" ] || { echo "ERROR: source tree incomplete" >&2; exit 1; }
[ -f "$VERSION_FILE" ] || { echo "ERROR: existing plugin not detected; use install.sh for initial installation" >&2; exit 1; }
CURRENT=$(cat "$VERSION_FILE")
case "$CURRENT" in 3.*) ;; *) echo "ERROR: upgrade from $CURRENT requires a migration plan; refusing" >&2; exit 1;; esac
NEXT=$(sed -n 's/^PLUGIN_VERSION="\([^"]*\)"/\1/p' "$ROOT/install.sh" | head -1)
[ -n "$NEXT" ] || { echo "ERROR: cannot determine target version" >&2; exit 1; }
[ -f /conf/config.xml ] || { echo "ERROR: /conf/config.xml missing" >&2; exit 1; }
[ -f /usr/local/opnsense/scripts/Xray/xray-service-control.php ] || { echo "ERROR: controller missing" >&2; exit 1; }

echo "Existing plugin: $CURRENT; target source: $NEXT"
echo "No Xray-core/tun2socks restart, no Apply, no config.xml migration."
echo "Requires a healthy working configd; CLI/GUI control pauses briefly during its restart."
printf 'Continue [y/N]? '
read answer || exit 1
case "$answer" in y|Y|yes|YES) ;; *) echo "Cancelled"; exit 0;; esac

STAMP=$(date +%Y%m%d-%H%M%S)
BACKUP="/root/os-xray-upgrade-$STAMP"
mkdir -m 0700 "$BACKUP"
cp -p /conf/config.xml "$BACKUP/config.xml"
cp -p "$VERSION_FILE" "$BACKUP/version.txt"
# Capture only plugin-owned files; do not back up or overwrite private tunnel configs.
tar -czf "$BACKUP/plugin-files.tar.gz" -C / \
    usr/local/opnsense/scripts/Xray \
    usr/local/opnsense/service/conf/actions.d/actions_xray.conf \
    usr/local/opnsense/mvc/app/models/OPNsense/Xray \
    usr/local/opnsense/mvc/app/controllers/OPNsense/Xray \
    usr/local/opnsense/mvc/app/views/OPNsense/Xray \
    usr/local/etc/inc/plugins.inc.d/xray.inc \
    usr/local/etc/rc.syshook.d/start/50-xray
echo "Backup: $BACKUP"

# Validate all PHP before modifying the installed tree.
find "$SRC" -type f -name '*.php' | while IFS= read -r file; do
    php -l "$file" >/dev/null || exit 1
done

install_tree() {
    src=$1 dst=$2 mode=$3
    (cd "$src" && find . -type d -print) | while IFS= read -r rel; do
        install -d "$dst/$rel"
    done
    (cd "$src" && find . -type f -print) | while IFS= read -r rel; do
        install -m "$mode" "$src/$rel" "$dst/$rel"
    done
}
install_tree "$SRC/scripts/Xray" /usr/local/opnsense/scripts/Xray 0755
install_tree "$SRC/service/conf/actions.d" /usr/local/opnsense/service/conf/actions.d 0644
install_tree "$SRC/mvc/app/models/OPNsense/Xray" /usr/local/opnsense/mvc/app/models/OPNsense/Xray 0644
install_tree "$SRC/mvc/app/controllers/OPNsense/Xray" /usr/local/opnsense/mvc/app/controllers/OPNsense/Xray 0644
install_tree "$SRC/mvc/app/views/OPNsense/Xray" /usr/local/opnsense/mvc/app/views/OPNsense/Xray 0644
install_tree "$SRC/etc/inc/plugins.inc.d" /usr/local/etc/inc/plugins.inc.d 0644
install_tree "$SRC/etc/rc.syshook.d/start" /usr/local/etc/rc.syshook.d/start 0755
install_tree "$SRC/etc/newsyslog.conf.d" /etc/newsyslog.conf.d 0644
printf '%s\n' "$NEXT" > "$VERSION_FILE"
rm -f /var/lib/php/tmp/opnsense_menu_cache.xml

# configd caches actions at startup; reload only its control daemon, not VPN processes.
service configd restart
# Refresh OPNsense-generated cron after updated plugin autocron hooks.
php -r '
require_once("/usr/local/etc/inc/config.inc");
require_once("/usr/local/etc/inc/util.inc");
require_once("/usr/local/etc/inc/system.inc");
system_cron_configure();
'
echo "Updated control files. Verify status, PIDs, TUN and a no-op Apply manually."
echo "Backup preserved at $BACKUP"
