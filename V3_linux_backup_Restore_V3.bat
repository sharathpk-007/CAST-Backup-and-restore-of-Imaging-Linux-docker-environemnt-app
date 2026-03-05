@echo off
setlocal enabledelayedexpansion

:: #################################################################################
:: # CAST Imaging Backup & Restore Utility - Command-Line Interface
:: #
:: # Author:  AI Assistant
:: # Version: 1.0
:: # Desc:    This script replicates the functionality of the Python utility
:: #            using standard Windows CLI tools (PLINK, PSCP).
:: #################################################################################

title CAST Imaging Backup & Restore Utility CLI

:CHECK_PREREQUISITES
echo Checking for prerequisites...
where plink >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo ERROR: 'plink.exe' was not found in your system PATH.
    echo Please install the PuTTY suite from https://www.putty.org/
    echo Ensure the option "Add PuTTY to the system PATH" is checked during installation.
    echo.
    pause
    exit /b 1
)
where pscp >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo ERROR: 'pscp.exe' was not found in your system PATH.
    echo Please install the PuTTY suite from https://www.putty.org/
    echo Ensure the option "Add PuTTY to the system PATH" is checked during installation.
    echo.
    pause
    exit /b 1
)
echo Prerequisites found.
echo.
pause
goto :MENU

:: ####################
:: # MAIN MENU
:: ####################
:MENU
cls
echo ======================================================================
echo          CAST Imaging Backup & Restore Utility CLI
echo ======================================================================
echo.
echo Please select an operation:
echo.
echo   [1] Run Backup on Source Server
echo   [2] Transfer Backup from Source to Destination
echo   [3] Restore Files & Infrastructure on Destination Server
echo   [4] Restore Database & Finalize on Destination Server
echo   -----------------------------------------------------
echo   [5] Run ALL Steps (Backup, Transfer, and Restore)
echo.
echo   [6] Exit
echo.
set /p "CHOICE=Enter your choice [1-6]: "

if /I "%CHOICE%"=="1" (call :GET_SOURCE_VARS & call :BACKUP & goto :MENU)
if /I "%CHOICE%"=="2" (call :GET_SOURCE_VARS & call :GET_DEST_VARS & call :TRANSFER & goto :MENU)
if /I "%CHOICE%"=="3" (call :GET_DEST_VARS & call :RESTORE_FILES & goto :MENU)
if /I "%CHOICE%"=="4" (call :GET_DEST_VARS & call :RESTORE_DB & goto :MENU)
if /I "%CHOICE%"=="5" (call :GET_ALL_VARS & call :RUN_ALL & goto :MENU)
if /I "%CHOICE%"=="6" (exit /b)
echo Invalid choice. Please try again.
pause
goto :MENU

:: ####################
:: # RUN ALL STEPS IN SEQUENCE
:: ####################
:RUN_ALL
call :BACKUP
if %errorlevel% neq 0 ( echo CRITICAL ERROR in Backup step. Aborting. & pause & exit /b 1 )
call :TRANSFER
if %errorlevel% neq 0 ( echo CRITICAL ERROR in Transfer step. Aborting. & pause & exit /b 1 )
call :RESTORE_FILES
if %errorlevel% neq 0 ( echo CRITICAL ERROR in Restore Files step. Aborting. & pause & exit /b 1 )
call :RESTORE_DB
if %errorlevel% neq 0 ( echo CRITICAL ERROR in Restore DB step. Aborting. & pause & exit /b 1 )
echo.
echo =========================================================
echo == ALL STEPS COMPLETED SUCCESSFULLY!
echo =========================================================
echo.
pause
goto :EOF

:: ####################
:: # VARIABLE INPUT
:: ####################
:GET_ALL_VARS
call :GET_SOURCE_VARS
call :GET_DEST_VARS
goto :EOF

:GET_SOURCE_VARS
if defined SOURCE_IP ( goto :EOF )
cls
echo --- Enter Source Server Details ---
set /p "SOURCE_IP=Source IP Address: "
set /p "SOURCE_USER=Source Username [support]: "
if "%SOURCE_USER%"=="" set SOURCE_USER=support
set /p "SOURCE_PASS=Source SSH Password: "
set /p "SOURCE_SUDO_PASS=Source Sudo Password (if different, else leave blank): "
if "%SOURCE_SUDO_PASS%"=="" set "SOURCE_SUDO_PASS=%SOURCE_PASS%"
echo.
echo --- Enter Source PostgreSQL Details ---
set /p "SOURCE_PG_CONTAINER=Source PG Container ID: "
set /p "SOURCE_PG_HOST=Source PG Host IP (IP inside Docker network): "
set /p "SOURCE_PG_USER=Source PG User [operator]: "
if "%SOURCE_PG_USER%"=="" set SOURCE_PG_USER=operator
set /p "SOURCE_PG_PASS=Source PG Password: "
set /p "SOURCE_PG_PORT=Source PG Port [2285]: "
if "%SOURCE_PG_PORT%"=="" set SOURCE_PG_PORT=2285
set /p "SOURCE_PG_DBNAME=Source PG DB Name [postgres]: "
if "%SOURCE_PG_DBNAME%"=="" set SOURCE_PG_DBNAME=postgres
set /p "SOURCE_PG_SCHEMA=Source PG Schema [control_panel]: "
if "%SOURCE_PG_SCHEMA%"=="" set SOURCE_PG_SCHEMA=control_panel
goto :EOF

:GET_DEST_VARS
if defined DEST_IP ( goto :EOF )
cls
echo --- Enter Destination Server Details ---
set /p "DEST_IP=Destination IP Address: "
set /p "DEST_USER=Destination Username [support]: "
if "%DEST_USER%"=="" set DEST_USER=support
set /p "DEST_PASS=Destination SSH Password: "
set /p "DEST_SUDO_PASS=Destination Sudo Password (if different, else leave blank): "
if "%DEST_SUDO_PASS%"=="" set "DEST_SUDO_PASS=%DEST_PASS%"
echo.
echo --- Enter Installer Options (Required for Restore) ---
set /p "INSTALLER_VER=Installer Version (e.g., 3.4.0-funcrel): "
set /p "API_KEY=Extend API Key: "
echo.
echo --- Enter Destination PostgreSQL Details (Required for Finalize) ---
set /p "DEST_PG_CONTAINER=Destination PG Container ID (run 'docker ps' on dest): "
set /p "DEST_PG_USER=Destination PG User [operator]: "
if "%DEST_PG_USER%"=="" set DEST_PG_USER=operator
set /p "DEST_PG_PASS=Destination PG Password: "
set /p "DEST_PG_PORT=Destination PG Port [2285]: "
if "%DEST_PG_PORT%"=="" set DEST_PG_PORT=2285
set /p "DEST_PG_DBNAME=Destination PG DB Name [postgres]: "
if "%DEST_PG_DBNAME%"=="" set DEST_PG_DBNAME=postgres
set /p "DEST_PG_SCHEMA=Destination PG Schema [control_panel]: "
if "%DEST_PG_SCHEMA%"=="" set DEST_PG_SCHEMA=control_panel
goto :EOF


:: ##########################################################################
:: #                         CORE LOGIC FUNCTIONS
:: ##########################################################################

:: ####################
:: # STEP 1: BACKUP
:: ####################
:BACKUP
cls
echo ======================================================
echo == STEP 1: RUNNING BACKUP ON SOURCE SERVER...
echo ======================================================
set TIMESTAMP=%date:~10,4%%date:~4,2%%date:~7,2%_%time:~0,2%%time:~3,2%%time:~6,2%
set TIMESTAMP=%TIMESTAMP: =0%
set REMOTE_BACKUP_DIR=/home/%SOURCE_USER%/cast_backup_%TIMESTAMP%

echo.
echo [1/3] Creating remote backup directory: %REMOTE_BACKUP_DIR%
plink.exe -ssh %SOURCE_USER%@%SOURCE_IP% -pw %SOURCE_PASS% "mkdir -p %REMOTE_BACKUP_DIR%"
if %errorlevel% neq 0 ( echo ERROR! Failed to create directory. & goto :FAIL )

echo.
echo [2/3] Creating tarball of /opt/cast...
plink.exe -ssh %SOURCE_USER%@%SOURCE_IP% -pw %SOURCE_PASS% "echo '%SOURCE_SUDO_PASS%' | sudo -S tar -czvf %REMOTE_BACKUP_DIR%/opt_cast_backup.tar.gz /opt/cast"
if %errorlevel% neq 0 ( echo ERROR! Failed to create tarball. & goto :FAIL )

echo.
echo [3/3] Dumping PostgreSQL database...
set "PG_DUMP_CMD=docker exec -e PGPASSWORD='%SOURCE_PG_PASS%' %SOURCE_PG_CONTAINER% /bin/bash -c 'pg_dump -U %SOURCE_PG_USER% -h %SOURCE_PG_HOST% -p %SOURCE_PG_PORT% -d %SOURCE_PG_DBNAME% --schema=%SOURCE_PG_SCHEMA% -F c' > %REMOTE_BACKUP_DIR%/control_panel_schema.backup"
plink.exe -ssh %SOURCE_USER%@%SOURCE_IP% -pw %SOURCE_PASS% "!PG_DUMP_CMD!"
if %errorlevel% neq 0 ( echo ERROR! Failed to dump database. & goto :FAIL )

echo.
echo ------------------------------------------------------
echo BACKUP SUCCEEDED. Remote backup path is: %REMOTE_BACKUP_DIR%
echo ------------------------------------------------------
echo.
pause
goto :EOF


:: ####################
:: # STEP 2: TRANSFER
:: ####################
:TRANSFER
cls
echo ======================================================
echo == STEP 2: TRANSFERRING BACKUP TO DESTINATION...
echo ======================================================
if not defined REMOTE_BACKUP_DIR (
    echo WARNING: No backup path found. Please provide it.
    set /p "REMOTE_BACKUP_DIR=Path to backup on source server: "
)

set "LOCAL_BACKUP_FOLDER=%~dp0%REMOTE_BACKUP_DIR:/=_%"
set "LOCAL_BACKUP_FOLDER=%LOCAL_BACKUP_FOLDER:\=/%"
set "LOCAL_BACKUP_FOLDER=%LOCAL_BACKUP_FOLDER::=%
set "LOCAL_BACKUP_FOLDER=%LOCAL_BACKUP_FOLDER:~3%"
set "LOCAL_BACKUP_FOLDER=%LOCAL_BACKUP_FOLDER:/=\%"


echo.
echo [1/3] Downloading backup from source server...
pscp.exe -pw %SOURCE_PASS% -r %SOURCE_USER%@%SOURCE_IP%:%REMOTE_BACKUP_DIR% .
if %errorlevel% neq 0 ( echo ERROR! Failed to download backup. & goto :FAIL )

echo.
set "BACKUP_BASENAME=%REMOTE_BACKUP_DIR%/=" & for %%a in ("!BACKUP_BASENAME!") do set "BACKUP_BASENAME=%%~nxa"
echo [2/3] Uploading backup to destination server...
pscp.exe -pw %DEST_PASS% -r "!BACKUP_BASENAME!" %DEST_USER%@%DEST_IP%:/home/%DEST_USER%/
if %errorlevel% neq 0 ( echo ERROR! Failed to upload backup. & goto :FAIL )

echo.
echo [3/3] Cleaning up local temporary files...
rmdir /s /q "!BACKUP_BASENAME!"

set "REMOTE_RESTORE_PATH=/home/%DEST_USER%/!BACKUP_BASENAME!"
echo.
echo ------------------------------------------------------
echo TRANSFER SUCCEEDED. Backup is now at %REMOTE_RESTORE_PATH%
echo ------------------------------------------------------
echo.
pause
goto :EOF

:: ####################
:: # STEP 3: RESTORE FILES
:: ####################
:RESTORE_FILES
cls
echo ======================================================
echo == STEP 3: RESTORING FILES & INFRASTRUCTURE...
echo ======================================================
if not defined REMOTE_RESTORE_PATH (
    echo WARNING: No restore path found. Please provide it.
    set /p "REMOTE_RESTORE_PATH=Path to backup on destination server: "
)
set "TAR_FILE=!REMOTE_RESTORE_PATH!/opt_cast_backup.tar.gz"

echo.
echo [1/7] Downloading CAST Imaging Installer (if needed)...
plink.exe -ssh %DEST_USER%@%DEST_IP% -pw %DEST_PASS% "cd %REMOTE_RESTORE_PATH% && [ ! -f *.zip ] && curl -# -O -J 'https://extend.castsoftware.com/api/package/download/com.castsoftware.imaging.all.docker/%INSTALLER_VER%?platform=linux_x64' -H 'x-nuget-apikey: %API_KEY%' -H 'accept: application/octet-stream' || echo 'Installer zip already exists.'"
if %errorlevel% neq 0 ( echo ERROR! Failed to download installer. Check version and API Key. & goto :FAIL )

echo.
echo [2/7] Extracting /opt/cast backup...
plink.exe -ssh %DEST_USER%@%DEST_IP% -pw %DEST_PASS% "mkdir -p %REMOTE_RESTORE_PATH%/temp_extract && tar -xzf %TAR_FILE% -C %REMOTE_RESTORE_PATH%/temp_extract"
if %errorlevel% neq 0 ( echo ERROR! Failed to extract tarball. & goto :FAIL )

echo.
echo [3/7] Syncing files to /opt directory...
plink.exe -ssh %DEST_USER%@%DEST_IP% -pw %DEST_PASS% "echo '%DEST_SUDO_PASS%' | sudo -S rsync -av --delete %REMOTE_RESTORE_PATH%/temp_extract/opt/ /opt/"
if %errorlevel% neq 0 ( echo ERROR! Failed to sync files with rsync. & goto :FAIL )

echo.
echo [4/7] Correcting file ownership...
plink.exe -ssh %DEST_USER%@%DEST_IP% -pw %DEST_PASS% "echo '%DEST_SUDO_PASS%' | sudo -S chown -R %DEST_USER%:%DEST_USER% /opt/cast"
if %errorlevel% neq 0 ( echo ERROR! Failed to change ownership. & goto :FAIL )

echo.
echo [5/7] Updating IP address in .env files...
for %%s in (imaging-services imaging-node imaging-dashboards) do (
    plink.exe -ssh %DEST_USER%@%DEST_IP% -pw %DEST_PASS% "cd /opt/cast/installation/%%s && [ -f .env ] && sed -i 's/^HOST_HOSTNAME=.*/HOST_HOSTNAME=%DEST_IP%/' .env"
)

echo.
echo [6/7] Pulling Docker images...
for %%s in (imaging-services imaging-node imaging-dashboards) do (
    echo   - Pulling for %%s...
    plink.exe -ssh %DEST_USER%@%DEST_IP% -pw %DEST_PASS% "cd /opt/cast/installation/%%s && docker compose pull"
)

echo.
echo [7/7] Starting PostgreSQL service and cleaning up...
plink.exe -ssh %DEST_USER%@%DEST_IP% -pw %DEST_PASS% "cd /opt/cast/installation/imaging-services && docker compose up -d"
if %errorlevel% neq 0 ( echo ERROR! Failed to start imaging-services. & goto :FAIL )
echo   - Waiting 20 seconds for PG to initialize...
timeout /t 20 /nobreak >nul
plink.exe -ssh %DEST_USER%@%DEST_IP% -pw %DEST_PASS% "cd /opt/cast/installation/imaging-services && docker compose stop keycloak eureka-server"
plink.exe -ssh %DEST_USER%@%DEST_IP% -pw %DEST_PASS% "rm -rf %REMOTE_RESTORE_PATH%/temp_extract"

echo.
echo ------------------------------------------------------
echo RESTORE FILES & INFRASTRUCTURE SUCCEEDED.
echo ------------------------------------------------------
echo.
pause
goto :EOF

:: ####################
:: # STEP 4: RESTORE DB & FINALIZE
:: ####################
:RESTORE_DB
cls
echo ======================================================
echo == STEP 4: RESTORING DATABASE & FINALIZING...
echo ======================================================
if not defined REMOTE_RESTORE_PATH (
    echo WARNING: No restore path found. Please provide it.
    set /p "REMOTE_RESTORE_PATH=Path to backup on destination server: "
)
set "PG_BACKUP_FILE=!REMOTE_RESTORE_PATH!/control_panel_schema.backup"

echo.
echo [1/5] Restoring database schema...
set "PG_RESTORE_CMD=cat %PG_BACKUP_FILE% | docker exec -i -e PGPASSWORD='%DEST_PG_PASS%' %DEST_PG_CONTAINER% /bin/bash -c 'pg_restore -U %DEST_PG_USER% -h localhost -p 5432 -d %DEST_PG_DBNAME% --clean'"
plink.exe -ssh %DEST_USER%@%DEST_IP% -pw %DEST_PASS% "!PG_RESTORE_CMD!"
if %errorlevel% neq 0 ( echo ERROR! Failed to restore database. & goto :FAIL )

echo.
echo [2/5] Updating database properties with new IP...
set "SQL_CMD_1=UPDATE %DEST_PG_SCHEMA%.properties SET value = 'http://%DEST_IP%:8090' WHERE prop_key = 'keycloak.uri';"
set "SQL_CMD_2=UPDATE %DEST_PG_SCHEMA%.properties SET value = '%DEST_IP%' WHERE prop_key = 'eureka.host';"
set "SQL_CMD_3=UPDATE %DEST_PG_SCHEMA%.properties SET value = 'jdbc:postgresql://%DEST_IP%:%DEST_PG_PORT%/%DEST_PG_DBNAME%?currentSchema=%DEST_PG_SCHEMA%' WHERE prop_key = 'spring.datasource.url';"
plink.exe -ssh %DEST_USER%@%DEST_IP% -pw %DEST_PASS% "docker exec -e PGPASSWORD='%DEST_PG_PASS%' %DEST_PG_CONTAINER% psql -U %DEST_PG_USER% -d %DEST_PG_DBNAME% -c ""!SQL_CMD_1!"" "
plink.exe -ssh %DEST_USER%@%DEST_IP% -pw %DEST_PASS% "docker exec -e PGPASSWORD='%DEST_PG_PASS%' %DEST_PG_CONTAINER% psql -U %DEST_PG_USER% -d %DEST_PG_DBNAME% -c ""!SQL_CMD_2!"" "
plink.exe -ssh %DEST_USER%@%DEST_IP% -pw %DEST_PASS% "docker exec -e PGPASSWORD='%DEST_PG_PASS%' %DEST_PG_CONTAINER% psql -U %DEST_PG_USER% -d %DEST_PG_DBNAME% -c ""!SQL_CMD_3!"" "

echo.
echo [3/5] Updating ETL configuration...
plink.exe -ssh %DEST_USER%@%DEST_IP% -pw %DEST_PASS% "export ZIPFILE=$(ls -1 %REMOTE_RESTORE_PATH%/*.zip | head -n 1) && unzip -o ""$ZIPFILE"" -d %REMOTE_RESTORE_PATH%/unzipped_installer"
plink.exe -ssh %DEST_USER%@%DEST_IP% -pw %DEST_PASS% "cd %REMOTE_RESTORE_PATH%/unzipped_installer/cast-imaging-viewer && chmod +x imagingsetup && ./imagingsetup -hn '%DEST_IP%' -ch '%DEST_IP%' -cp '8098' -d '/opt/cast/installation/imaging-viewer' -ofl -u update"
if %errorlevel% neq 0 ( echo ERROR! Failed to run imagingsetup. & goto :FAIL )

echo.
echo [4/5] Starting all application services...
for %%s in (imaging-services imaging-node imaging-dashboards) do (
    echo   - Starting %%s...
    plink.exe -ssh %DEST_USER%@%DEST_IP% -pw %DEST_PASS% "cd /opt/cast/installation/%%s && docker compose up -d"
)

echo.
echo [5/5] Final cleanup...
plink.exe -ssh %DEST_USER%@%DEST_IP% -pw %DEST_PASS% "rm -rf %REMOTE_RESTORE_PATH%/unzipped_installer"

echo.
echo ------------------------------------------------------
echo DATABASE RESTORE & FINALIZE SUCCEEDED.
echo The application should now be running on the destination server.
echo ------------------------------------------------------
echo.
pause
goto :EOF

:: ####################
:: # FAILURE HANDLER
:: ####################
:FAIL
echo.
echo !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
echo !! AN ERROR OCCURRED. Please review the logs above.
echo !! The script cannot continue.
echo !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
echo.
pause
exit /b 1