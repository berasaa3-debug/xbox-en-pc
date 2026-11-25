@echo off
title Crear Xbox en PC.exe
python -m pip install --upgrade pip
python -m pip install pyinstaller
python -m PyInstaller --noconfirm --clean --onefile --windowed --name "Xbox en PC" xbox_en_pc.py
echo.
echo Listo. Tu aplicacion esta en la carpeta dist.
pause
