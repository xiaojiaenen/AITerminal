"""安全策略引擎测试。"""

import pytest
from ai_terminal.safety.policy import SafetyPolicy, RiskLevel, Decision


class TestSafetyPolicy:
    """SafetyPolicy 测试。"""

    def setup_method(self):
        self.policy = SafetyPolicy()

    # --- SAFE 级别 ---

    def test_safe_commands(self):
        safe_cmds = [
            "ls -la",
            "cat /etc/passwd",
            "head -n 10 file.txt",
            "grep pattern file.txt",
            "ps aux",
            "df -h",
            "free -m",
            "uptime",
            "whoami",
            "git status",
            "git log --oneline",
            "docker ps",
            "docker images",
            "echo hello",
        ]
        for cmd in safe_cmds:
            result = self.policy.classify(cmd)
            assert result == RiskLevel.SAFE, f"'{cmd}' should be SAFE, got {result}"

    # --- LOW 级别 ---

    def test_low_commands(self):
        low_cmds = [
            "touch newfile.txt",
            "mkdir newdir",
            "cp file1 file2",
            "mv file1 file2",
            "pip install requests",
            "npm install lodash",
            "git add .",
            "git commit -m 'test'",
            "docker run nginx",
            "docker stop container",
            "chmod 755 script.sh",
        ]
        for cmd in low_cmds:
            result = self.policy.classify(cmd)
            assert result == RiskLevel.LOW, f"'{cmd}' should be LOW, got {result}"

    # --- HIGH 级别 ---

    def test_high_commands(self):
        high_cmds = [
            "rm file.txt",
            "rm -rf dir/",
            "docker rm container",
            "git reset --hard HEAD~1",
            "git push --force",
            "systemctl stop nginx",
            "iptables -L",
            "mysql -e 'DELETE FROM users'",
        ]
        for cmd in high_cmds:
            result = self.policy.classify(cmd)
            assert result == RiskLevel.HIGH, f"'{cmd}' should be HIGH, got {result}"

    # --- CRITICAL 级别 ---

    def test_critical_commands(self):
        critical_cmds = [
            "rm -rf /",
            "rm -rf ~",
            "rm -rf *",
            "mkfs.ext4 /dev/sda1",
            "dd if=/dev/zero of=/dev/sda",
            "shutdown -h now",
            "reboot",
            "DROP DATABASE production",
            "TRUNCATE TABLE users",
        ]
        for cmd in critical_cmds:
            result = self.policy.classify(cmd)
            assert result == RiskLevel.CRITICAL, f"'{cmd}' should be CRITICAL, got {result}"

    # --- check 方法 ---

    def test_check_safe_auto_approve(self):
        decision = self.policy.check("ls -la")
        assert decision.allowed is True
        assert decision.risk_level == RiskLevel.SAFE
        assert decision.require_confirmation is False

    def test_check_low_auto_approve(self):
        decision = self.policy.check("touch newfile")
        assert decision.allowed is True
        assert decision.risk_level == RiskLevel.LOW
        assert decision.require_confirmation is False

    def test_check_high_needs_confirmation(self):
        decision = self.policy.check("rm file.txt")
        assert decision.allowed is True
        assert decision.risk_level == RiskLevel.HIGH
        assert decision.require_confirmation is True

    def test_check_critical_needs_confirmation(self):
        decision = self.policy.check("rm -rf /")
        assert decision.allowed is True
        assert decision.risk_level == RiskLevel.CRITICAL
        assert decision.require_confirmation is True

    # --- 白名单 ---

    def test_whitelist(self):
        policy = SafetyPolicy({"whitelist": ["rm -rf /tmp/cache"]})
        decision = policy.check("rm -rf /tmp/cache")
        assert decision.allowed is True
        assert decision.risk_level == RiskLevel.SAFE

    # --- 黑名单 ---

    def test_blacklist(self):
        policy = SafetyPolicy({"blacklist": ["make coffee"]})
        decision = policy.check("make coffee")
        assert decision.allowed is False
        assert decision.risk_level == RiskLevel.CRITICAL

    # --- 替代方案 ---

    def test_alternative_for_rm(self):
        decision = self.policy.check("rm file.txt")
        assert decision.alternative is not None
        assert "trash" in decision.alternative.lower() or "mv" in decision.alternative.lower()

    def test_alternative_for_force_push(self):
        decision = self.policy.check("git push --force")
        assert decision.alternative is not None
        assert "force-with-lease" in decision.alternative

    # --- 未知命令 ---

    def test_unknown_command_is_high(self):
        result = self.policy.classify("some_random_command arg1 arg2")
        assert result == RiskLevel.HIGH

    # --- 自定义规则 ---

    def test_custom_rules(self):
        policy = SafetyPolicy({
            "custom_rules": [
                {"pattern": r"^my-deploy\b", "level": "critical"},
            ]
        })
        assert policy.classify("my-deploy production") == RiskLevel.CRITICAL
        assert policy.classify("ls") == RiskLevel.SAFE
