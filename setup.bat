@echo off
set "ICON_PATH=%~dp0Icons\Vamp.ico"

echo Registering Vamp (.vp) file association and icon...

reg add "HKCU\Software\Classes\.vp" /ve /d "VampSourceFile" /f >nul
reg add "HKCU\Software\Classes\VampSourceFile" /ve /d "Vamp Language Source File" /f >nul
reg add "HKCU\Software\Classes\VampSourceFile\DefaultIcon" /ve /d "\"%ICON_PATH%\",0" /f >nul

ie4uinit.exe -show >nul 2>&1

echo Vamp file association complete!
pause
