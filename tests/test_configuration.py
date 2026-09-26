#!/usr/bin/env python3
from pathlib import Path
import hashlib
import json
import subprocess
import unittest

ROOT = Path.home() / ".local/share/tuwien-vpn"
CONTROLLER = ROOT / "src/tuwien-vpnctl"
CLI = ROOT / "src/tuvpn"
VPNC = ROOT / "src/vpnc-script"
RUNTIME = ROOT / "build/tuwien-openconnect-9.21"
MANIFEST = RUNTIME / "manifest.json"


class ConfigurationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.controller = CONTROLLER.read_text()
        cls.cli = CLI.read_text()
        cls.vpnc = VPNC.read_text()

    def test_shell_syntax(self):
        for path in (CONTROLLER, CLI, VPNC):
            subprocess.run(["/bin/bash" if path != VPNC else "/bin/sh", "-n", str(path)], check=True)

    def test_cli_has_only_needed_commands(self):
        self.assertIn("usage: $0 {status|connect|disconnect|doctor|logs}", self.controller)
        self.assertIn("connect)", self.cli)
        self.assertIn("disconnect)", self.cli)
        self.assertIn("status)", self.cli)
        self.assertIn("doctor)", self.cli)
        self.assertIn("logs)", self.cli)
        for marker in ("connect|split", "disconnect|stop", "reconnect)", "nudge)",
                       "full)", "debug)", "repair-dns)", "watchdog)", "desired-state)"):
            self.assertNotIn(marker, self.cli)
            self.assertNotIn(marker, self.controller)

    def test_long_term_token_is_not_in_argv(self):
        self.assertIn("--token-secret=@/dev/fd/3", self.controller)
        self.assertNotIn('--token-secret="$token_secret"', self.controller)

    def test_privileged_runtime_is_root_owned_copy(self):
        self.assertIn(
            "readonly OPENCONNECT='/usr/local/libexec/tuwien-openconnect-9.21/bin/openconnect'",
            self.controller,
        )
        self.assertIn("P11_KIT_NO_USER_CONFIG=1", self.controller)
        self.assertIn("--no-proxy", self.controller)
        self.assertIn("--no-dtls", self.controller)
        self.assertIn("--csd-wrapper=/usr/bin/false", self.controller)

    def test_healthcheck_uses_real_vpn_dns_response(self):
        healthcheck = self.controller.split("vpn_healthcheck() {", 1)[1].split("\n}", 1)[0]
        self.assertIn("/usr/bin/dig", healthcheck)
        self.assertIn("/usr/bin/grep -Eq", healthcheck)
        self.assertNotIn("nc -G 2 -z", healthcheck)

    def test_dns_and_keychain_failures_are_explicitly_handled(self):
        resolver_body = self.controller.split("resolve_vpn_host_public_ipv4() {", 1)[1].split("\nvpn_dns_state_keys() {", 1)[0]
        self.assertIn(") || true", resolver_body)
        keychain_body = self.controller.split("openconnect_cmd() {", 1)[1].split("\nwait_for_status_up() {", 1)[0]
        self.assertIn("read_credentials", self.controller)
        self.assertIn("external_trusted", keychain_body)
        self.assertIn("TUW_PASS", keychain_body)
        self.assertIn("TUW_SEED", keychain_body)
        self.assertIn("security find-generic-password", self.cli)
        self.assertIn("printf '%s\\n%s\\n%s\\n'", self.cli)
        self.assertIn("return 1", keychain_body)

    def test_openconnect_output_is_captured_to_log_file(self):
        self.assertIn("readonly LOG_FILE=", self.controller)
        body = self.controller.split("openconnect_cmd() {", 1)[1].split("\nwait_for_status_up() {", 1)[0]
        self.assertIn("prepare_log_file", body)
        self.assertIn('>>"$LOG_FILE" 2>&1', body)

    def test_logs_command_reads_log_file(self):
        self.assertIn("logs) logs_impl ;;", self.controller)
        self.assertIn("logs_impl() {", self.controller)
        self.assertIn("connect_summary()", self.controller)
        self.assertIn("print_recent_log()", self.controller)
        self.assertIn("run_ctl logs", self.cli)

    def test_no_background_supervisor_or_state_machine(self):
        for marker in ("watchdog", "desired_state", "desired-state", "WATCHDOG_STATE_FILE",
                       "nudge_impl", "reconnect_impl", "debug_report", "kill -USR2"):
            self.assertNotIn(marker, self.controller)
        self.assertFalse((ROOT / "src/tuwien-vpn-watchdog").exists())
        self.assertFalse((ROOT / "TUvpn.applescript").exists())

    def test_lock_removal_verifies_pid_match(self):
        body = self.controller.split("with_lock() {", 1)[1].split("\n}", 1)[0]
        self.assertIn("current_pid", body)
        self.assertIn('"$current_pid" == "$lock_pid"', body)

    def test_install_script_is_portable_and_complete(self):
        install = (ROOT / "install.sh").read_text()
        self.assertNotIn("/Users/samuel", install)
        self.assertIn('SOURCE_ROOT="$(cd "$(dirname "$0")" && pwd)"', install)
        self.assertIn("/usr/sbin/chown root:wheel", install)
        for marker in ("SUDOERS_FILE", "visudo -cf", "vendor_runtime.py", "manifest"):
            self.assertIn(marker, install)
        self.assertNotIn("WATCHDOG_SOURCE", install)
        self.assertIn("bootout", install)
        self.assertNotIn("bootstrap", install)
        self.assertNotIn("osacompile", install)
        self.assertNotIn(".bak.", install)
        self.assertNotIn("skipping verification", install)
        self.assertIn("refusing unverified runtime installation", install)
        self.assertIn("Then: tuvpn connect", install)

    def test_runtime_manifest_verifies_without_self_hash(self):
        manifest = json.loads(MANIFEST.read_text())
        files = manifest["files"]
        self.assertNotIn("manifest.json", files)
        for relative_path, expected in files.items():
            path = RUNTIME / relative_path
            self.assertTrue(path.is_file(), relative_path)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected,
                             relative_path)

    def test_manifest_builder_excludes_manifest_itself(self):
        builder = (ROOT / "vendor_runtime.py").read_text()
        self.assertIn("p != manifest_path", builder)

    def test_pid_is_validated_before_signals(self):
        self.assertIn("pid_is_openconnect", self.controller)
        self.assertIn("Refusing to signal unrelated process", self.controller)

    def test_connect_when_already_up_is_noop(self):
        connect_body = self.controller.split("connect_impl() {", 1)[1].split("\ndoctor() {", 1)[0]
        self.assertIn('if [[ "$(status || true)" == up ]]; then', connect_body)
        self.assertIn("cleanup_stale_state", connect_body)
        self.assertIn("repair_dns", connect_body)
        self.assertNotIn("set_desired", connect_body)
        self.assertNotIn("PRESERVE_DESIRED_STATE", connect_body)

    def test_dns_configuration_is_volatile(self):
        self.assertNotIn("networksetup", self.controller)
        self.assertNotIn("DNS_SNAPSHOT_FILE", self.controller)
        executable_lines = [
            line for line in self.vpnc.splitlines()
            if "networksetup" in line and not line.lstrip().startswith("#")
        ]
        self.assertEqual(executable_lines, [])
        self.assertIn("SupplementalMatchDomains", self.vpnc)
        self.assertIn("State:/Network/Service/$TUNDEV/DNS", self.vpnc)

    def test_full_tunnel_mode_is_removed(self):
        self.assertNotIn("AUTHGROUP_FULL", self.controller)
        self.assertNotIn("CURRENT_PROFILE", self.controller)
        self.assertNotIn("select_profile", self.controller)
        self.assertNotIn("saved_profile", self.controller)
        self.assertNotIn("PROFILE_FILE", self.controller)
        self.assertIn("readonly AUTHGROUP='1_TU_getunnelt'", self.controller)
        self.assertNotIn("connect full", self.cli)


if __name__ == "__main__":
    unittest.main(verbosity=2)
