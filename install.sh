#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

install -m 0755 tuwien-vpnctl /usr/local/sbin/tuwien-vpnctl
mkdir -p "$HOME/.local/bin"
install -m 0755 tuvpn "$HOME/.local/bin/tuvpn"

echo "Installed tuwien-vpnctl -> /usr/local/sbin/tuwien-vpnctl"
echo "Installed tuvpn        -> $HOME/.local/bin/tuvpn"
echo "Run 'tuvpn doctor' to verify."
