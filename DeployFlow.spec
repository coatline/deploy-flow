# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['deployflow/__main__.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['keyring.backends.Windows'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['numpy', 'pandas', 'PIL', 'matplotlib', 'scipy'],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DeployFlow',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='DeployFlow',
)
