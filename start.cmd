@echo off
rem gatepack — Windows entry point (thin shim over start.ps1).
rem
rem   start.cmd              the desktop app
rem   start.cmd dev          the desktop app with renderer live-reload
rem   start.cmd cli ARGS...  the command-line core
rem   start.cmd doctor       report what is installed and what is missing
rem
rem This file only hands off to start.ps1 (the real implementation, which
rem shares one copy of the logic and prints a readable message — never a stack
rem trace — when a prerequisite is absent). Run `start.cmd help` for usage.

setlocal
where powershell >nul 2>nul
if errorlevel 1 (
  echo error: PowerShell is not available. Install Windows PowerShell 5.1^
 ^(built into Windows 10^) and re-run, or use `start.ps1` from an existing shell.
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
exit /b %errorlevel%
