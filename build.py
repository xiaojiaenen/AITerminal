"""构建脚本 — 使用 PyInstaller 打包为单个可执行文件。"""

import subprocess
import sys
import os
from pathlib import Path

PROJECT_DIR = Path(__file__).parent
ENTRY = PROJECT_DIR / "ai_terminal" / "__main__.py"
DIST_DIR = PROJECT_DIR / "dist"
BUILD_DIR = PROJECT_DIR / "build"


def build():
    """构建可执行文件。"""
    print("开始构建 AI Terminal...")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",                          # 单文件
        "--console",                          # 控制台应用
        "--name", "ai-terminal",              # 输出文件名
        "--distpath", str(DIST_DIR),
        "--workpath", str(BUILD_DIR),
        "--clean",                            # 清理临时文件
        # 收集整个包
        "--collect-all", "ai_terminal",
        # wuwei 只收集子包，避免拉入 dev 依赖
        "--collect-submodules", "wuwei",
        # 隐藏导入
        "--hidden-import", "asyncssh",
        "--hidden-import", "prompt_toolkit",
        "--hidden-import", "rich",
        "--hidden-import", "yaml",
        "--hidden-import", "pydantic",
        "--hidden-import", "aiohttp",
        # 排除不需要的模块
        "--exclude-module", "tkinter",
        "--exclude-module", "tkinter",
        "--exclude-module", "matplotlib",
        "--exclude-module", "numpy",
        "--exclude-module", "pandas",
        "--exclude-module", "PIL",
        "--exclude-module", "cv2",
        "--exclude-module", "torch",
        "--exclude-module", "tensorflow",
        "--exclude-module", "onnxruntime",
        "--exclude-module", "pypdf",
        "--exclude-module", "pypdfium2",
        "--exclude-module", "pdfplumber",
        "--exclude-module", "openpyxl",
        "--exclude-module", "pptx",
        "--exclude-module", "magika",
        "--exclude-module", "lxml",
        "--exclude-module", "mammoth",
        "--exclude-module", "markitdown",
        "--exclude-module", "speech_recognition",
        "--exclude-module", "pydub",
        str(ENTRY),
    ]

    print(f"执行: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(PROJECT_DIR))

    if result.returncode == 0:
        exe_path = DIST_DIR / "ai-terminal.exe"
        if exe_path.exists():
            size_mb = exe_path.stat().st_size / (1024 * 1024)
            print(f"\n构建成功！")
            print(f"输出: {exe_path}")
            print(f"大小: {size_mb:.1f} MB")
        else:
            exe_path = DIST_DIR / "ai-terminal"
            if exe_path.exists():
                size_mb = exe_path.stat().st_size / (1024 * 1024)
                print(f"\n构建成功！")
                print(f"输出: {exe_path}")
                print(f"大小: {size_mb:.1f} MB")
    else:
        print(f"\n构建失败，退出码: {result.returncode}")
        sys.exit(1)


if __name__ == "__main__":
    build()
