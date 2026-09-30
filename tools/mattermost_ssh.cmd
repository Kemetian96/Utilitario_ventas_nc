@echo off
setlocal enabledelayedexpansion
rem Abre PuTTY con la sesion de Mattermost (SRVKUB) ya iniciada.
rem La clave NO esta aqui: se lee del .env del proyecto cada vez que se abre.
rem Con MM_DRYRUN=1 solo muestra lo que leyo, sin conectarse.

set "ENVFILE=%~dp0..\.env"
set "PUTTY=C:\Program Files\PuTTY\putty.exe"

if not exist "%ENVFILE%" (
  echo No encuentro el archivo de configuracion: %ENVFILE%
  pause
  exit /b 1
)

for /f "usebackq eol=# tokens=1,* delims==" %%A in ("%ENVFILE%") do (
  if /i "%%A"=="MATTERMOST_SSH_HOST"     set "MMHOST=%%B"
  if /i "%%A"=="MATTERMOST_SSH_PORT"     set "MMPORT=%%B"
  if /i "%%A"=="MATTERMOST_SSH_USER"     set "MMUSER=%%B"
  if /i "%%A"=="MATTERMOST_SSH_PASSWORD" set "MMPASS=%%B"
)

rem Quita espacios sobrantes al final, que en el .env pasan desapercibidos.
:trim_pass
if defined MMPASS if "!MMPASS:~-1!"==" " set "MMPASS=!MMPASS:~0,-1!" & goto trim_pass
:trim_host
if defined MMHOST if "!MMHOST:~-1!"==" " set "MMHOST=!MMHOST:~0,-1!" & goto trim_host
:trim_user
if defined MMUSER if "!MMUSER:~-1!"==" " set "MMUSER=!MMUSER:~0,-1!" & goto trim_user
:trim_port
if defined MMPORT if "!MMPORT:~-1!"==" " set "MMPORT=!MMPORT:~0,-1!" & goto trim_port
if not defined MMPORT set "MMPORT=22"

if not defined MMHOST goto falta
if not defined MMUSER goto falta
if not defined MMPASS goto falta

if "%MM_DRYRUN%"=="1" (
  echo host....: !MMHOST!
  echo puerto..: !MMPORT!
  echo usuario.: !MMUSER!
  echo clave...: !MMPASS:~0,1!********!MMPASS:~-1!
  echo putty...: %PUTTY%
  exit /b 0
)

if not exist "%PUTTY%" (
  echo No encuentro PuTTY en: %PUTTY%
  pause
  exit /b 1
)

rem -pw entrega la clave por el metodo "password", el unico que acepta este
rem servidor: tiene KbdInteractiveAuthentication apagado y por eso el login
rem a mano en PuTTY salia denegado.
start "" "%PUTTY%" -ssh !MMUSER!@!MMHOST! -P !MMPORT! -pw !MMPASS!
exit /b 0

:falta
echo Al .env le faltan datos de Mattermost ^(host, usuario o clave^).
pause
exit /b 1
