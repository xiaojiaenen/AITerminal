"""踩坑记录器测试。"""

import tempfile
from pathlib import Path

from ai_terminal.runtime.incident import IncidentRecorder


class TestIncidentRecorder:
    """IncidentRecorder 测试。"""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.recorder = IncidentRecorder(store_path=self.tmpdir)

    def test_record_failure(self):
        incident = self.recorder.record(
            command="apt install nginx",
            exit_code=127,
            error_output="bash: apt: command not found",
        )
        assert incident is not None
        assert incident.exit_code == 127
        assert incident.root_cause == "命令未安装"
        assert "install" in incident.solution

    def test_record_success_returns_none(self):
        result = self.recorder.record(
            command="ls",
            exit_code=0,
            error_output="",
        )
        assert result is None

    def test_permission_denied_pattern(self):
        incident = self.recorder.record(
            command="./script.sh",
            exit_code=126,
            error_output="Permission denied",
        )
        assert incident is not None
        assert incident.root_cause == "权限不足"

    def test_port_in_use_pattern(self):
        incident = self.recorder.record(
            command="python app.py",
            exit_code=1,
            error_output="OSError: [Errno 98] Address already in use",
        )
        assert incident is not None
        assert incident.root_cause == "端口被占用"

    def test_disk_full_pattern(self):
        incident = self.recorder.record(
            command="dd if=/dev/zero of=test bs=1M",
            exit_code=1,
            error_output="dd: error writing 'test': No space left on device",
        )
        assert incident is not None
        assert incident.root_cause == "磁盘空间不足"

    def test_unknown_error(self):
        incident = self.recorder.record(
            command="some_cmd",
            exit_code=1,
            error_output="Something weird happened",
        )
        assert incident is not None
        assert incident.root_cause == ""  # 未知错误不自动填充

    def test_search(self):
        self.recorder.record("apt install nginx", 127, "command not found")
        self.recorder.record("pip install flask", 1, "No module named 'flask'")

        results = self.recorder.search("command not found")
        assert len(results) >= 1

    def test_stats(self):
        self.recorder.record("apt install nginx", 127, "command not found")
        self.recorder.record("pip install flask", 1, "ModuleNotFoundError")

        stats = self.recorder.get_stats()
        assert stats["total"] == 2
        assert stats["resolved"] == 2  # 已知模式自动标记为已解决

    def test_persistence(self):
        self.recorder.record("apt install nginx", 127, "command not found")

        # 重新加载
        recorder2 = IncidentRecorder(store_path=self.tmpdir)
        assert len(recorder2._incidents) == 1
        assert recorder2._incidents[0].root_cause == "命令未安装"

    def test_generate_skill(self):
        incident = self.recorder.record("apt install nginx", 127, "command not found")
        assert incident is not None

        path = self.recorder.generate_skill(incident)
        assert Path(path).exists()
        assert incident.skill_generated is True

        content = Path(path).read_text(encoding="utf-8")
        assert "命令未安装" in content

    def test_mark_resolved(self):
        incident = self.recorder.record(
            command="custom_cmd",
            exit_code=1,
            error_output="Weird error",
        )
        assert incident is not None
        assert incident.resolved is False

        self.recorder.mark_resolved(incident.id, "do this instead")
        assert incident.resolved is True
        assert incident.solution == "do this instead"
