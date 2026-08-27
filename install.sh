#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

# Only the privileged install needs sudo; the user-facing wrapper goes to
# $HOME/.local/bin and must NOT be root-owned.
sudo install -m 0755 tuwien-vpnctl /usr/local/sbin/tuwien-vpnctl
mkdir -p "$HOME/.local/bin"
install -m 0755 tuvpn "$HOME/.local/bin/tuvpn"

echo "Installed tuwien-vpnctl -> /usr/local/sbin/tuwien-vpnctl (root)"
echo "Installed tuvpn        -> $HOME/.local/bin/tuvpn"
echo "Run 'tuvpn doctor' to verify."
