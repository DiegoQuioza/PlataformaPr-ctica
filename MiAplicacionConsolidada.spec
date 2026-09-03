# -*- mode: python ; coding: utf-8 -*-

import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# 1. Mapeo explicito de carpetas y archivos estaticos
# Sintaxis: ('ruta_origen_en_disco', 'ruta_destino_en_exe')
added_datas = [
    ('templates', 'templates'),
    ('static', 'static'),
    ('plugins', 'plugins'),
    ('routes', 'routes'),
    ('docs', 'docs'),
    # Archivos JSON de palabras clave y mapeos
    ('plugins/medioambiente/riles/automatizaciones/lectorPdf/*.json', 'plugins/medioambiente/riles/automatizaciones/lectorPdf'),
]

# 2. Recoleccion automatica de submodulos para evitar ModuleNotFoundError
# Dado que cargas lectores de PDF y plugins dinamicamente
hidden_imports = [
    'sqlite3',
    'jinja2',
    'openpyxl',
    'pandas',
    'pdfplumber',
    'pypdf',
    'fitz',  # PyMuPDF si lo utilizas
] 

# Recolectar dinamicamente todos los submodulos dentro de core y plugins
hidden_imports += collect_submodules('core')
hidden_imports += collect_submodules('plugins')

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=added_datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'unittest'],  # Excluir librerias innecesarias para reducir tamaño
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
    name='MiAplicacionConsolidada',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,  # Comprime binarios si UPX esta instalado
    console=True,  # Cambiar a False si NO deseas que se abra la ventana de consola CMD
    icon=None,     # Puedes especificar un icono: icon='static/src/app.ico'
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='MiAplicacionConsolidada',
)