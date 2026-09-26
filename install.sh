#!/bin/bash
set -euo pipefail
PATH='/usr/bin:/bin:/usr/sbin:/sbin'
export PATH

# Derive all paths from this script's location so it is portable.
SOURCE_ROOT="$(cd "$(dirname "$0")" && pwd)"
readonly SOURCE_ROOT
readonly RUNTIME_SOURCE="$SOURCE_ROOT/build/tuwien-openconnect-9.21"
readonly RUNTIME_DEST='/usr/local/libexec/tuwien-openconnect-9.21'
readonly CONTROLLER_SOURCE="$SOURCE_ROOT/src/tuwien-vpnctl"
readonly CONTROLLER_DEST='/usr/local/sbin/tuwien-vpnctl'
readonly TUVPN_SOURCE="$SOURCE_ROOT/src/tuvpn"
readonly VENDOR_RUNTIME="$SOURCE_ROOT/vendor_runtime.py"
readonly SUDOERS_FILE='/etc/sudoers.d/tuwien-vpnctl'

# --- Determine the target user (the real human, not root) -------------------
if [[ $# -ge 1 ]]; then
  TARGET_USER=$1
elif [[ -n "${SUDO_USER:-}" ]]; then
  TARGET_USER=$SUDO_USER
else
  TARGET_USER=$(stat -f '%Su' /dev/console 2>/dev/null || echo "$USER")
fi
if ! id "$TARGET_USER" >/dev/null 2>&1; then
  echo "Unknown user: $TARGET_USER" >&2
  exit 1
fi
TARGET_UID=$(id -u "$TARGET_USER")
TARGET_GID=$(id -g "$TARGET_USER")
TARGET_HOME=$(eval echo "~$TARGET_USER")
readonly TARGET_USER TARGET_UID TARGET_GID TARGET_HOME

readonly USER_BIN="$TARGET_HOME/.local/bin"

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo 'install.sh must run as root (try: sudo ./install.sh)' >&2
  exit 1
fi

echo "Installing TUvpn for user: $TARGET_USER ($TARGET_HOME)"

# --- 1. Build the vendored OpenConnect runtime if missing ------------------
if [[ ! -x "$RUNTIME_SOURCE/bin/openconnect" ]]; then
  echo 'Vendored runtime not found; building with vendor_runtime.py...'
  # vendor_runtime.py reads Homebrew paths; run as the target user so Homebrew
  # is discoverable, then chown the result.
  /usr/bin/sudo -u "$TARGET_USER" /usr/bin/python3 "$VENDOR_RUNTIME"
fi

[[ -x "$RUNTIME_SOURCE/bin/openconnect" ]] || { echo 'vendored OpenConnect runtime is missing' >&2; exit 1; }
[[ -x "$RUNTIME_SOURCE/scripts/vpnc-script" ]] || { echo 'vendored vpnc-script is missing' >&2; exit 1; }
[[ -x "$CONTROLLER_SOURCE" ]] || { echo 'controller source is missing' >&2; exit 1; }

# --- 2. Validate the manifest sha256s before installing --------------------
MANIFEST="$RUNTIME_SOURCE/manifest.json"
if [[ -f "$MANIFEST" ]]; then
  /usr/bin/python3 - "$MANIFEST" "$RUNTIME_SOURCE" <<'PY' || { echo 'manifest verification failed' >&2; exit 1; }
import hashlib, json, sys
manifest_path, root = sys.argv[1], sys.argv[2]
with open(manifest_path) as f:
    manifest = json.load(f)
for rel, expected in manifest.get("files", {}).items():
    path = __import__("pathlib").Path(root) / rel
    if not path.is_file():
        sys.exit(f"missing file: {rel}")
    h = hashlib.sha256()
    with path.open("rb") as s:
        for chunk in iter(lambda: s.read(1024 * 1024), b""):
            h.update(chunk)
    if h.hexdigest() != expected:
        sys.exit(f"hash mismatch: {rel}")
print(f"manifest verified ({len(manifest['files'])} files)")
PY
else
  echo 'manifest.json is missing; refusing unverified runtime installation' >&2
  exit 1
fi

/bin/bash -n "$CONTROLLER_SOURCE"

# --- 3. Install the root-owned OpenConnect runtime -------------------------
/usr/bin/install -d -o root -g wheel -m 755 /usr/local/libexec /usr/local/sbin
/usr/bin/install -d -o root -g wheel -m 755 "$RUNTIME_DEST"
/usr/bin/ditto --noqtn "$RUNTIME_SOURCE" "$RUNTIME_DEST"
/usr/sbin/chown -R root:wheel "$RUNTIME_DEST"
/usr/bin/find "$RUNTIME_DEST" -type d -exec /bin/chmod 755 {} +
/usr/bin/find "$RUNTIME_DEST" -type f -exec /bin/chmod 644 {} +
/bin/chmod 755 "$RUNTIME_DEST/bin/openconnect" "$RUNTIME_DEST/scripts/vpnc-script"

# Refuse an installation that still links executable code from user-owned Homebrew.
if /usr/bin/find "$RUNTIME_DEST/bin" "$RUNTIME_DEST/lib" "$RUNTIME_DEST/pkcs11" -type f -print0 \
  | /usr/bin/xargs -0 -n1 /usr/bin/otool -L \
  | /usr/bin/grep -q '/opt/homebrew/'; then
  echo 'installed runtime still contains Homebrew load commands' >&2
  exit 1
fi
"$RUNTIME_DEST/bin/openconnect" --version

# --- 4. Install the root-owned controller ---------------------------------
/usr/bin/install -o root -g wheel -m 755 "$CONTROLLER_SOURCE" "$CONTROLLER_DEST"
/bin/bash -n "$CONTROLLER_DEST"

# --- 5. Create the sudoers NOPASSWD entry ---------------------------------
echo "$TARGET_USER ALL=(root) NOPASSWD: $CONTROLLER_DEST" > "$SUDOERS_FILE"
/usr/sbin/chown root:wheel "$SUDOERS_FILE"
/bin/chmod 0440 "$SUDOERS_FILE"
visudo -cf "$SUDOERS_FILE" || { echo 'sudoers syntax check failed' >&2; exit 1; }

# --- 6. Install the user-facing wrappers ----------------------------------
/usr/bin/install -d -o "$TARGET_UID" -g "$TARGET_GID" -m 755 "$USER_BIN"
/usr/bin/install -o "$TARGET_UID" -g "$TARGET_GID" -m 755 "$TUVPN_SOURCE" "$USER_BIN/tuvpn"

# Remove files from older installations. No background supervisor is needed:
# OpenConnect handles transport reconnects; the controller cleans stale state
# before connect and during disconnect.
/bin/launchctl bootout "gui/$TARGET_UID/at.tuwien.vpn-watchdog" 2>/dev/null || true
/bin/rm -f "$USER_BIN/tuwien-vpn-watchdog" \
  "$TARGET_HOME/Library/LaunchAgents/at.tuwien.vpn-watchdog.plist" \
  "$TARGET_HOME/Library/Logs/tuwien-vpn-watchdog.log" \
  /var/run/tuwien-vpn.desired-state /var/run/tuwien-vpn-watchdog.state \
  /var/run/tuwien-vpn.dns-snapshot

echo
echo 'TUvpn installed successfully.'
echo
echo 'Remaining manual step — add Keychain items:'
echo "  security add-generic-password -a '$TARGET_USER@tuwien.ac.at' -s 'TUWien VPN Password' -w"
echo "  security add-generic-password -a '$TARGET_USER@tuwien.ac.at' -s 'TUWien VPN TOTP Seed' -w"
echo
echo 'Then: tuvpn connect'
