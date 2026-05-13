"""构建脚本 — 使用 PyInstaller 打包为单个可执行文件（跨平台）。"""

import subprocess
import sys
from pathlib import Path

# Windows CI 强制 UTF-8 输出，避免中文/emoji 乱码
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_DIR = Path(__file__).parent
ENTRY = PROJECT_DIR / "ai_terminal" / "__main__.py"
DIST_DIR = PROJECT_DIR / "dist"
BUILD_DIR = PROJECT_DIR / "build"

IS_WINDOWS = sys.platform == "win32"
EXE_SUFFIX = ".exe" if IS_WINDOWS else ""

EXCLUDES = [
    "tkinter", "matplotlib", "numpy", "pandas", "PIL", "cv2",
    "torch", "tensorflow", "onnxruntime", "pypdf", "pypdfium2",
    "pdfplumber", "openpyxl", "pptx", "magika", "lxml", "mammoth",
    "markitdown", "speech_recognition", "pydub",
]

HIDDEN_IMPORTS = [
    "asyncssh", "prompt_toolkit", "rich", "yaml", "pydantic", "aiohttp",
]


def build():
    """构建可执行文件。"""
    print(f"开始构建 AI Terminal ({sys.platform})...")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--console",
        "--name", "ai-terminal",
        "--distpath", str(DIST_DIR),
        "--workpath", str(BUILD_DIR),
        "--clean",
        "--collect-all", "ai_terminal",
        "--collect-submodules", "wuwei",
    ]
    for mod in HIDDEN_IMPORTS:
        cmd += ["--hidden-import", mod]
    for mod in EXCLUDES:
        cmd += ["--exclude-module", mod]
    cmd.append(str(ENTRY))

    print(f"执行: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(PROJECT_DIR))

    exe_path = DIST_DIR / f"ai-terminal{EXE_SUFFIX}"

    if result.returncode == 0 and exe_path.exists():
        size_mb = exe_path.stat().st_size / (1024 * 1024)
        print(f"\n构建成功！")
        print(f"平台: {sys.platform}")
        print(f"输出: {exe_path}")
        print(f"大小: {size_mb:.1f} MB")
    else:
        print(f"\n构建失败，退出码: {result.returncode}")
        sys.exit(1)


if __name__ == "__main__":
    build()
