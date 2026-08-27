# tuvpn — TU Wien split-tunnel VPN for macOS

Thin wrapper around `tuwien-vpnctl`, a bash controller for the TU Wien
OpenConnect client. Split tunnel only. **No credentials live in this repo** —
your password and TOTP seed stay in your own macOS Keychain.

## Requirements

- macOS
- The TU Wien openconnect build at `/usr/local/libexec/tuwien-openconnect-9.21/`
  (bin + `scripts/vpnc-script`). Install it first; the script currently
  hardcodes that path.
- `~/.local/bin` on `PATH` (openconnect is invoked by root, unprivileged bits go
  to `~/.local/bin`).

## Setup

```bash
git clone https://github.com/SamuelBadr/tuvpn-tuwien.git
cd tuvpn-tuwien
./install.sh                     # sudo only for the /usr/local/sbin controller
```

Store your own secrets in your Keychain — never commit these (use your own
account name; `tuvpn` will ask for it if `TUWIEN_CUID` isn't exported):

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

- `tuvpn` resolves your account (`TUWIEN_CUID` or a prompt) and reads the
  password + TOTP seed from your *login* Keychain as the unprivileged user,
  then hands them to the privileged controller over stdin. They never appear in
  command lines, the environment, or on disk; install your own secrets with
  `tuvpn doctor` guiding you.
- If any command reports *timed out waiting for lock*, a watchdog is wedged
  (held the lock past its timeout); `disconnect`/`connect` stop it automatically
  when the lock is still its own.
- `tuvpn` cannot be run through `sudo` directly for `connect`: run it as your
  normal user so the Keychain can be read.
- A launchd agent on the author's machine runs `tuwien-vpnctl watchdog` every
  30s. It only nudges/recovers a session you already started: it never
  authenticates (it runs as root, outside your Keychain). If the tunnel is gone
  it reports `authentication-required`; run `tuvpn connect` to re-establish. The
  watchdog lives in the controller; the agent itself is machine-local and not
  part of this repo.
