"""安全策略引擎测试（跨平台）。"""

import sys
import pytest
from ai_terminal.safety.policy import SafetyPolicy, RiskLevel, Decision


def _is_windows() -> bool:
    return sys.platform == "win32"


class TestSafetyPolicy:
    """SafetyPolicy 测试。"""

    def setup_method(self):
        self.policy = SafetyPolicy()

    # --- 跨平台通用 SAFE 命令 ---

    def test_safe_commands_cross_platform(self):
        """测试跨平台通用的 SAFE 命令。"""
        safe_cmds = [
            "git status",
            "git log --oneline",
            "git diff",
            "git branch",
            "git remote -v",
            "docker ps",
            "docker images",
            "docker logs container",
            "docker inspect container",
            "docker stats",
            "echo hello",
            "whoami",
            "hostname",
        ]
        for cmd in safe_cmds:
            result = self.policy.classify(cmd)
            assert result == RiskLevel.SAFE, f"'{cmd}' should be SAFE, got {result}"

    # --- Linux/macOS SAFE 命令 ---

    @pytest.mark.skipif(_is_windows(), reason="Linux/macOS only")
    def test_safe_commands_unix(self):
        """测试 Unix 特有的 SAFE 命令。"""
        safe_cmds = [
            "ls -la",
            "cat /etc/passwd",
            "head -n 10 file.txt",
            "grep pattern file.txt",
            "ps aux",
            "df -h",
            "free -m",
            "uptime",
            "ping google.com",
        ]
        for cmd in safe_cmds:
            result = self.policy.classify(cmd)
            assert result == RiskLevel.SAFE, f"'{cmd}' should be SAFE, got {result}"

    # --- Windows SAFE 命令 ---

    @pytest.mark.skipif(not _is_windows(), reason="Windows only")
    def test_safe_commands_windows(self):
        """测试 Windows 特有的 SAFE 命令。"""
        safe_cmds = [
            "dir",
            "dir /w",
            "type file.txt",
            "ipconfig",
            "ipconfig /all",
            "tasklist",
            "systeminfo",
            "net user",
            "netstat -an",
            "Get-Process",
            "Get-Service",
            "Get-ChildItem",
            "Get-Content file.txt",
            "Select-Object",
            "Where-Object",
            "Test-Path",
        ]
        for cmd in safe_cmds:
            result = self.policy.classify(cmd)
            assert result == RiskLevel.SAFE, f"'{cmd}' should be SAFE, got {result}"

    # --- 跨平台通用 LOW 命令 ---

    def test_low_commands_cross_platform(self):
        """测试跨平台通用的 LOW 命令。"""
        low_cmds = [
            "git add .",
            "git commit -m 'test'",
            "git push",
            "git pull",
            "git checkout main",
            "git merge feature",
            "git stash",
            "docker run nginx",
            "docker start container",
            "docker stop container",
            "docker compose up",
            "docker compose down",
            "pip install requests",
            "npm install lodash",
        ]
        for cmd in low_cmds:
            result = self.policy.classify(cmd)
            assert result == RiskLevel.LOW, f"'{cmd}' should be LOW, got {result}"

    # --- Linux/macOS LOW 命令 ---

    @pytest.mark.skipif(_is_windows(), reason="Linux/macOS only")
    def test_low_commands_unix(self):
        """测试 Unix 特有的 LOW 命令。"""
        low_cmds = [
            "touch newfile.txt",
            "mkdir newdir",
            "cp file1 file2",
            "mv file1 file2",
            "chmod 755 script.sh",
            "apt install nginx",
            "yum install httpd",
            "brew install git",
        ]
        for cmd in low_cmds:
            result = self.policy.classify(cmd)
            assert result == RiskLevel.LOW, f"'{cmd}' should be LOW, got {result}"

    # --- Windows LOW 命令 ---

    @pytest.mark.skipif(not _is_windows(), reason="Windows only")
    def test_low_commands_windows(self):
        """测试 Windows 特有的 LOW 命令。"""
        low_cmds = [
            "mkdir newdir",
            "copy file1 file2",
            "move file1 file2",
            "ren oldname newname",
            "New-Item -Path test.txt",
            "Copy-Item src dst",
            "Move-Item src dst",
            "Start-Service servicename",
            "Stop-Service servicename",
            "Invoke-WebRequest url",
        ]
        for cmd in low_cmds:
            result = self.policy.classify(cmd)
            assert result == RiskLevel.LOW, f"'{cmd}' should be LOW, got {result}"

    # --- 跨平台通用 HIGH 命令 ---

    def test_high_commands_cross_platform(self):
        """测试跨平台通用的 HIGH 命令。"""
        high_cmds = [
            "docker rm container",
            "docker kill container",
            "docker rmi image",
            "git reset --hard HEAD~1",
            "git push --force",
            "git branch -D feature",
            "git clean -f",
            "mysql -e 'DELETE FROM users'",
            "mysql -e 'DROP TABLE test'",
        ]
        for cmd in high_cmds:
            result = self.policy.classify(cmd)
            assert result == RiskLevel.HIGH, f"'{cmd}' should be HIGH, got {result}"

    # --- Linux/macOS HIGH 命令 ---

    @pytest.mark.skipif(_is_windows(), reason="Linux/macOS only")
    def test_high_commands_unix(self):
        """测试 Unix 特有的 HIGH 命令。"""
        high_cmds = [
            "rm file.txt",
            "rm -rf dir/",
            "systemctl stop nginx",
            "iptables -L",
            "shred file.txt",
        ]
        for cmd in high_cmds:
            result = self.policy.classify(cmd)
            assert result == RiskLevel.HIGH, f"'{cmd}' should be HIGH, got {result}"

    # --- Windows HIGH 命令 ---

    @pytest.mark.skipif(not _is_windows(), reason="Windows only")
    def test_high_commands_windows(self):
        """测试 Windows 特有的 HIGH 命令。"""
        high_cmds = [
            "del file.txt",
            "del /f /q file.txt",
            "rd /s /q directory",
            "Remove-Item file.txt",
            "Stop-Process -Name notepad",
            "taskkill /PID 1234",
            "reg delete HKLM\\Software\\Test",
        ]
        for cmd in high_cmds:
            result = self.policy.classify(cmd)
            assert result == RiskLevel.HIGH, f"'{cmd}' should be HIGH, got {result}"

    # --- 跨平台通用 CRITICAL 命令 ---

    def test_critical_commands_cross_platform(self):
        """测试跨平台通用的 CRITICAL 命令。"""
        critical_cmds = [
            "DROP DATABASE production",
            "TRUNCATE TABLE users",
            "docker system prune -a",
            "docker volume rm data",
        ]
        for cmd in critical_cmds:
            result = self.policy.classify(cmd)
            assert result == RiskLevel.CRITICAL, f"'{cmd}' should be CRITICAL, got {result}"

    # --- Linux/macOS CRITICAL 命令 ---

    @pytest.mark.skipif(_is_windows(), reason="Linux/macOS only")
    def test_critical_commands_unix(self):
        """测试 Unix 特有的 CRITICAL 命令。"""
        critical_cmds = [
            "rm -rf /",
            "rm -rf ~",
            "rm -rf *",
            "mkfs.ext4 /dev/sda1",
            "dd if=/dev/zero of=/dev/sda",
            "shutdown -h now",
            "reboot",
            "halt",
            "poweroff",
            "chmod 777 /",
        ]
        for cmd in critical_cmds:
            result = self.policy.classify(cmd)
            assert result == RiskLevel.CRITICAL, f"'{cmd}' should be CRITICAL, got {result}"

    # --- Windows CRITICAL 命令 ---

    @pytest.mark.skipif(not _is_windows(), reason="Windows only")
    def test_critical_commands_windows(self):
        """测试 Windows 特有的 CRITICAL 命令。"""
        critical_cmds = [
            "del /s /q C:\\*",
            "rd /s /q C:\\",
            "format C:",
            "diskpart",
            "shutdown /s /t 0",
            "Remove-Item -Path C:\\ -Recurse -Force",
            "Clear-RecycleBin -Force",
            "Stop-Computer",
            "Restart-Computer",
        ]
        for cmd in critical_cmds:
            result = self.policy.classify(cmd)
            assert result == RiskLevel.CRITICAL, f"'{cmd}' should be CRITICAL, got {result}"

    # --- check 方法 ---

    def test_check_safe_auto_approve(self):
        decision = self.policy.check("git status")
        assert decision.allowed is True
        assert decision.risk_level == RiskLevel.SAFE
        assert decision.require_confirmation is False

    def test_check_low_auto_approve(self):
        decision = self.policy.check("git add .")
        assert decision.allowed is True
        assert decision.risk_level == RiskLevel.LOW
        assert decision.require_confirmation is False

    def test_check_high_needs_confirmation(self):
        decision = self.policy.check("docker rm container")
        assert decision.allowed is True
        assert decision.risk_level == RiskLevel.HIGH
        assert decision.require_confirmation is True

    def test_check_critical_needs_confirmation(self):
        decision = self.policy.check("DROP DATABASE production")
        assert decision.allowed is True
        assert decision.risk_level == RiskLevel.CRITICAL
        assert decision.require_confirmation is True

    # --- 白名单 ---

    def test_whitelist(self):
        policy = SafetyPolicy({"whitelist": ["docker rm temp"]})
        decision = policy.check("docker rm temp")
        assert decision.allowed is True
        assert decision.risk_level == RiskLevel.SAFE

    # --- 黑名单 ---

    def test_blacklist(self):
        policy = SafetyPolicy({"blacklist": ["make coffee"]})
        decision = policy.check("make coffee")
        assert decision.allowed is False
        assert decision.risk_level == RiskLevel.CRITICAL

    # --- 替代方案 ---

    def test_alternative_for_docker_rm(self):
        decision = self.policy.check("docker rm container")
        assert decision.alternative is not None
        assert "stop" in decision.alternative.lower()

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
        assert policy.classify("git status") == RiskLevel.SAFE
