@echo off
echo ============================================
echo   DeployFlow - Build Executable
echo ============================================
echo.

where pyinstaller >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing PyInstaller...
    pip install pyinstaller
)

echo Building DeployFlow.exe...
pyinstaller DeployFlow.spec --noconfirm

echo.
if exist "dist\DeployFlow\DeployFlow.exe" (
    echo SUCCESS: dist\DeployFlow\DeployFlow.exe
    echo.
    echo Copy the entire dist\DeployFlow folder anywhere.
    echo Run DeployFlow.exe from inside your game project folder.
) else (
    echo BUILD FAILED. Check the output above for errors.
)

pause
