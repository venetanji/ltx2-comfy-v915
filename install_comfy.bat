@echo off
setlocal EnableExtensions

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Install-Comfy.ps1"
exit /b %ERRORLEVEL%