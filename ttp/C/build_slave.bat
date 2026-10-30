@echo off
setlocal

cd /d "%~dp0"

gcc -std=c99 -Wall -Wextra -I "..\..\nanopb" -I "." -I "generated" "slave_main.c" "ttp.c" "generated\ttp.pb.c" "..\..\nanopb\pb_common.c" "..\..\nanopb\pb_decode.c" "..\..\nanopb\pb_encode.c" -o "ttp_slave.exe"

exit /b %errorlevel%
