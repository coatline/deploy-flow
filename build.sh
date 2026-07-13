#!/usr/bin/env bash
set -e

echo "============================================"
echo "  DeployFlow - Build Executable"
echo "============================================"
echo

if ! command -v pyinstaller &>/dev/null; then
    echo "Installing PyInstaller..."
    pip install pyinstaller
fi

echo "Building DeployFlow..."
pyinstaller DeployFlow.spec --noconfirm

echo
if [ -f "dist/DeployFlow/DeployFlow" ] || [ -f "dist/DeployFlow/DeployFlow.exe" ]; then
    echo "SUCCESS: dist/DeployFlow/"
    echo
    echo "Copy the entire dist/DeployFlow folder anywhere."
    echo "Run DeployFlow from inside your game project folder."
else
    echo "BUILD FAILED. Check the output above for errors."
fi
