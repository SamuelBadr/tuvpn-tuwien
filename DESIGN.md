# Design notes

## Goals

- Support TU Wien's split tunnel profile with mandatory MFA.
- Keep long-lived credentials in Keychain and out of argv/files/logs.
- Recover from ordinary transport changes without reauthentication.
- Use the HTTPS/CSTP data path; DTLS is disabled because it is unreliable on
  the current network path.
- Recover safely from process crashes without leaving default routes or DNS
  pointed at a dead tunnel.
- Avoid repeated unattended authentication that could lock the TU account.
- Minimize privileged and user-writable executable code.

## Architecture

A root-owned controller exposes a small command surface through the existing
scoped sudo policy. It launches a root-owned, relocated OpenConnect runtime and
a root-owned route/DNS script. The user-facing wrapper can therefore request
fixed operations but cannot substitute arbitrary executables or options.

OpenConnect performs normal in-process reconnection. No background supervisor
or desired-state file is needed: explicit `connect` and `disconnect` operations
clean up stale state at their boundaries.

## Crash recovery ordering

A split-tunnel crash can leave split-include routes and volatile DNS pointing
at a dead `utun`. The controller removes stale routes, VPN DNS state, and
per-session `vpnc-script` backups before a new `connect`, and during `disconnect`.
Because the physical default route is never modified in split mode, general
internet connectivity is never affected by a VPN crash.

## Security decisions

- Public CA validation is retained using macOS's CA bundle; there is no brittle
  leaf-certificate pin that would break at TU's next certificate renewal.
- `P11_KIT_NO_USER_CONFIG=1` prevents root OpenConnect from loading user-selected
  PKCS#11 modules.
- Homebrew Mach-O dependencies are copied, relocated, ad-hoc signed, and
  installed root-owned. Runtime validation rejects remaining Homebrew load
  commands.
- PID ownership is validated by executable path and TU host before sending any
  signal, preventing stale PID reuse from killing an unrelated process.
- The TOTP seed is supplied via an inherited descriptor rather than
  `--token-secret=base32:...` in argv.
- Credentials remain inside the user's Keychain boundary and MFA is manual;
  OpenConnect owns transport recovery without unattended reauthentication.
- OpenConnect stderr is captured to a root-owned `0600` log under
  `/var/run/tuwien-vpn/`; it carries no credentials because the password and
  TOTP seed travel via stdin and an inherited descriptor.
- Keychain unavailability (e.g. login keychain locked) fails closed with an
  explicit message rather than hanging. System-resolver hangs are bounded by
  `SIGALRM`; if the resolver still fails, connect falls back to a public-DNS
  `--resolve` address.

## Deliberate non-goals

- No private/reverse-engineered Apple Passwords API.
- No always-on VPN or connection at login.
- No silent Cisco removal; Cisco's official uninstaller remains the appropriate
  rollback-aware removal mechanism.
