@echo off
setlocal

REM Regenerate protobuf bindings for both TTP implementations.
REM Outputs are intentionally kept under each language folder so the hand-written
REM wrappers can include/import generated files from stable paths.

set "TTP_DIR=%~dp0"
set "REPO_ROOT=%TTP_DIR%.."
set "PROTO_DIR=%TTP_DIR%schema"
set "PROTO_FILE=%PROTO_DIR%\ttp.proto"
set "OPTIONS_FILE=%PROTO_DIR%\ttp.options"
set "C_OUT=%TTP_DIR%C\generated"
set "PY_OUT=%TTP_DIR%python\generated"
set "NANOPB_GENERATOR=%REPO_ROOT%\nanopb\generator\nanopb_generator.py"

if not exist "%C_OUT%" mkdir "%C_OUT%"
if not exist "%PY_OUT%" mkdir "%PY_OUT%"

python -m grpc_tools.protoc ^
  -I "%PROTO_DIR%" ^
  --python_out="%PY_OUT%" ^
  "%PROTO_FILE%"
if errorlevel 1 exit /b 1

python "%NANOPB_GENERATOR%" ^
  -I "%PROTO_DIR%" ^
  -D "%C_OUT%" ^
  -f "%OPTIONS_FILE%" ^
  "%PROTO_FILE%"
if errorlevel 1 exit /b 1

type nul > "%PY_OUT%\__init__.py"

echo Generated TTP protobuf files in:
echo   %C_OUT%
echo   %PY_OUT%

