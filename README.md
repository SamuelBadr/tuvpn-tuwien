# tuvpn — TU Wien split-tunnel VPN for macOS

A macOS-native replacement for Cisco Secure Client, built around OpenConnect
and TU Wien's AnyConnect-compatible endpoint. Split tunnel only: TU traffic goes
through the VPN, everything else stays on your normal connection. **No
credentials live in this repo** — your password and TOTP seed stay in your own
macOS Keychain.

## Setup

Requires Homebrew's `openconnect` (`brew install openconnect`) for the first
build, and `~/.local/bin` on your `PATH`.

```sh
git clone https://github.com/SamuelBadr/tuvpn-tuwien.git
cd tuvpn-tuwien
sudo ./install.sh
```

Store your secrets in the login Keychain (each command prompts for the value).
Use your own account; `tuvpn` reads it back from these items:

```sh
security add-generic-password -a you@tuwien.ac.at -s 'TUWien VPN Password' -w
security add-generic-password -a you@tuwien.ac.at -s 'TUWien VPN TOTP Seed' -w
```

Then `tuvpn doctor` and `tuvpn connect`. To update, `git pull` and re-run
`sudo ./install.sh`.

## Commands

```sh
tuvpn connect      # 1_TU_getunnelt — only TU traffic is tunneled
tuvpn disconnect   # clean disconnect and DNS restoration
tuvpn status       # up, degraded, or down
tuvpn doctor       # check runtime, Keychain, server, and secret handling
tuvpn logs         # show current-session OpenConnect output
```

`connect` first stops any existing session and cleans stale VPN routes/DNS, then
either ends with a healthy tunnel or leaves nothing behind. It never retries on
its own, so a failure costs one login attempt; just run it again. `disconnect`
performs the same cleanup, so no separate repair command or background
supervisor is needed.

## How it works

- **Credentials.** `tuvpn` reads the account, password and TOTP seed from your
  login Keychain as your normal user and passes them to the root controller
  over stdin. OpenConnect receives the password over stdin and the TOTP seed
  through an inherited file descriptor, so no secret appears in config files,
  logs, environment variables, or process arguments. Run `tuvpn` as your
  normal user, not through `sudo`, so it can read the Keychain.
- **Privileges.** `install.sh` installs a root-owned controller
  (`/usr/local/sbin/tuwien-vpnctl`), a passwordless sudo rule for exactly that
  file, and a root-owned copy of OpenConnect and its libraries
  (`/usr/local/libexec/tuwien-openconnect-9.21/`) built from Homebrew by
  `vendor_runtime.py`. Nothing user-writable runs as root.
- **Reconnection.** OpenConnect retries transport failures, Wi-Fi changes, and
  sleep/wake for up to 24 hours over HTTPS/CSTP (DTLS is disabled because the
  current network path corrupts its packets). If the process dies, run
  `tuvpn connect`.
- **DNS.** The bundled `vpnc-script` sends `*.tuwien.ac.at` to TU DNS through
  macOS's volatile `scutil` Dynamic Store only. It never writes persistent DNS
  settings, so a crash cannot leave Wi-Fi pointed at unreachable TU resolvers.
- **Logs.** OpenConnect's output goes to the root-only
  `/var/run/tuwien-vpn/openconnect.log`, truncated at each connect. On a failed
  connect the last 30 lines are shown.

See [DESIGN.md](DESIGN.md) for the reasoning behind these choices.
