: << 'CMDBLOCK'
@echo off
REM Windows: find a Python launcher and run the capture hook.
REM Capture must never break Claude Code, so every path exits 0.
set "DIR=%~dp0"
where py >nul 2>nul && (py -3 "%DIR%cmdvault.py" capture & exit /b 0)
where python >nul 2>nul && (python "%DIR%cmdvault.py" capture & exit /b 0)
exit /b 0
CMDBLOCK
# Unix: probe python3 then python; missing Python is a silent no-op.
DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
for p in python3 python; do
  if command -v "$p" >/dev/null 2>&1; then
    exec "$p" "$DIR/cmdvault.py" capture
  fi
done
exit 0
