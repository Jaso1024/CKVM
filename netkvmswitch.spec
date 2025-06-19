# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

# --- Data and Binary Files ---
ffmpeg_dll_path = 'C:\\Users\\jaboh\\Downloads\\ffmpeg-master-latest-win64-gpl-shared\\ffmpeg-master-latest-win64-gpl-shared\\bin'
binaries = [
    (ffmpeg_dll_path + '\\avcodec-62.dll', '.'),
    (ffmpeg_dll_path + '\\avdevice-62.dll', '.'),
    (ffmpeg_dll_path + '\\avfilter-11.dll', '.'),
    (ffmpeg_dll_path + '\\avformat-62.dll', '.'),
    (ffmpeg_dll_path + '\\avutil-60.dll', '.'),
    (ffmpeg_dll_path + '\\swresample-6.dll', '.'),
    (ffmpeg_dll_path + '\\swscale-9.dll', '.'),
]

datas = [
    ('netkvmswitch\\src', 'src'),
    ('certs', 'certs')
]

a = Analysis(
    ['netkvmswitch\\src\\bootstrap.py'],
    pathex=['C:\\Users\\jaboh\\Documents\\CKVM'],
    binaries=binaries,
    datas=datas,
    hiddenimports=['uvicorn', 'cv2', 'pynput', 'serial', 'serial.tools.list_ports', 'av', 'fastapi', 'fastapi.staticfiles'],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='NetKVMSwitch',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='NetKVMSwitch',
)
