# tuvpn — TU Wien split-tunnel VPN for macOS

Thin wrapper around `tuwien-vpnctl`, a bash controller for the TU Wien
OpenConnect client. Split tunnel only. **No credentials live in this repo** —
your password and TOTP seed stay in your own macOS Keychain.

## Requirements

- macOS
- The TU Wien openconnect build at `/usr/local/libexec/tuwien-openconnect-9.21/`
  (bin + `scripts/vpnc-script`). Install it first; the script currently
  hardcodes that path.
- `~/bin` on `PATH` (or symlink `~/.local/bin/tuvpn` yourself)

## Setup

```bash
git clone https://github.com/SamuelBadr/tuvpn-tuwien.git
cd tuvpn-tuwien
./install.sh                     # copies both files into place (asks for sudo)
```

Store your own secrets in your Keychain — never commit these (use your own
account name; `tuvpn` will also ask for it if you don't export it):

```bash
security add-generic-password -a "you@tuwien.ac.at" -s "TUWien VPN Password" -w
security add-generic-password -a "you@tuwien.ac.at" -s "TUWien VPN TOTP Seed" -w
```

(Keychain will prompt you to type each secret.)

Verify, then connect:

```bash
tuvpn doctor
tuvpn connect
```

## Usage

```
tuvpn connect|split   Connect (TU traffic only)
tuvpn disconnect      Disconnect cleanly, restore DNS
tuvpn reconnect       Re-authenticate
tuvpn nudge           Re-establish live session without fresh MFA
tuvpn status          up / degraded / down
tuvpn debug           Diagnostic report (no credentials)
tuvpn doctor          Check runtime, Keychain, server, secret handling
tuvpn repair-dns      Remove stale DNS state
tuvpn logs            Recent OpenConnect output
```

## Notes

- `tuvpn` prompts for your account name when `TUWIEN_CUID` isn't exported;
  export it to skip the prompt (e.g. `export TUWIEN_CUID=you@tuwien.ac.at` in
  `~/.zshrc`).
