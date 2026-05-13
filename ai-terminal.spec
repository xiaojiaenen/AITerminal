# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = ['asyncssh', 'prompt_toolkit', 'rich', 'yaml', 'pydantic', 'aiohttp']
hiddenimports += collect_submodules('wuwei')
tmp_ret = collect_all('ai_terminal')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['D:\\code\\AI-Terminal\\ai_terminal\\__main__.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'tkinter', 'matplotlib', 'numpy', 'pandas', 'PIL', 'cv2', 'torch', 'tensorflow', 'onnxruntime', 'pypdf', 'pypdfium2', 'pdfplumber', 'openpyxl', 'pptx', 'magika', 'lxml', 'mammoth', 'markitdown', 'speech_recognition', 'pydub'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='ai-terminal',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
