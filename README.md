# TU Wien VPN via OpenConnect

A macOS-native replacement for Cisco Secure Client, built around OpenConnect
9.21 and TU Wien's supported AnyConnect-compatible endpoint.

## Everyday commands

`~/.local/bin` is already on this account's `PATH`, so use:

```sh
tuvpn connect      # 1_TU_getunnelt — only TU traffic is tunneled
tuvpn disconnect   # clean disconnect and DNS restoration
tuvpn status       # up, degraded, or down
tuvpn doctor       # check runtime, Keychain, server, and secret handling
tuvpn logs         # show current-session OpenConnect output
```

`connect` cleans stale VPN routes/DNS before starting. `disconnect` performs the
same cleanup, so no separate repair command or background supervisor is needed.

## Credentials

The network password and TOTP seed are stored as generic items in the macOS
login Keychain. Apple Passwords does not expose verification codes through a
supported automation API, so the existing TOTP setup key is mirrored into a
Keychain item once. No password, current OTP, or TOTP seed appears in config
files, logs, environment variables, or process arguments.

OpenConnect receives the password over stdin and reads the TOTP seed through an
inherited file descriptor (`/dev/fd/3`).

## Reconnection

OpenConnect uses the authenticated HTTPS/CSTP tunnel and retries temporary
transport failures, Wi-Fi changes, and sleep/wake events for up to 24 hours.
DTLS is disabled because the current network path corrupts its packets. If the
process dies, run `tuvpn connect`; it cleans stale routes/DNS before asking for
MFA again.

## DNS and routing

The bundled `vpnc-script` uses only macOS's volatile `scutil` Dynamic Store for
VPN DNS. It never writes persistent DNS preferences with `networksetup`, so a
crash cannot leave Wi-Fi configured permanently with unreachable TU resolvers.

- Split mode sends `*.tuwien.ac.at` to TU DNS and leaves ordinary traffic/DNS on
  the physical connection.

## Logs

OpenConnect's output is captured to a root-owned file at
`/var/run/tuwien-vpn/openconnect.log` (mode `0600`). The file is truncated at
the start of each connect so `tuvpn logs` reflects the current session. It
contains no credentials: the password travels over stdin and the TOTP seed over
an inherited file descriptor, never via stderr.

During `tuvpn connect` only a short summary is printed (assigned addresses,
session expiry, pid). On a failed connect the last 30 log lines are shown to
aid diagnosis.

## Files

- User command: `~/.local/bin/tuvpn`
- Source/build/tests: `~/.local/share/tuwien-vpn/`
- Root controller: `/usr/local/sbin/tuwien-vpnctl`
- Root-owned runtime: `/usr/local/libexec/tuwien-openconnect-9.21/`
- Root-owned session log: `/var/run/tuwien-vpn/openconnect.log`

The root-owned runtime is a relocated copy of Homebrew OpenConnect and its
libraries. This avoids executing user-writable Homebrew code through the scoped
passwordless controller.
