#!/bin/bash

# #################################################################################
# # CAST Imaging Backup & Restore Utility - Linux Shell Script (Menu Driven)
# #
# # Author:  AI Assistant
# # Version: 2.1
# # Desc:    This script runs on the SOURCE server to perform a step-by-step
# #            migration to a DESTINATION server, pausing for user input.
# #################################################################################

# --- Configuration: ANSI Color Codes ---
C_RESET='\033[0m'
C_RED='\033[0;31m'
C_GREEN='\033[0;32m'
C_YELLOW='\033[0;33m'
C_CYAN='\033[0;36m'

# --- Helper Functions ---
function print_success { echo -e "${C_GREEN}[SUCCESS] $1${C_RESET}"; }
function print_error { echo -e "${C_RED}[ERROR] $1${C_RESET}"; }
function print_info { echo -e "${C_CYAN}[INFO] $1${C_RESET}"; }
function print_prompt { echo -e "${C_YELLOW}$1${C_RESET}"; }
function press_enter_to_continue { read -p "Press [Enter] to return to the main menu..."; }

function check_command {
    if ! command -v $1 &> /dev/null; then
        print_error "'$1' command not found. Please install it before running this script."
        exit 1
    fi
}

# --- Variable Input Functions ---
function gather_source_vars {
    if [ -z "$SOURCE_PG_CONTAINER" ]; then
        clear
        print_prompt "--- Step 1: Source Server Details (This Machine) ---"
        read -p "Enter your sudo password: " -s SUDO_PASS
        echo
        read -p "Source PG Container ID: " SOURCE_PG_CONTAINER
        read -p "Source PG Host IP (IP inside Docker network): " SOURCE_PG_HOST
        read -p "Source PG User [operator]: " SOURCE_PG_USER
        SOURCE_PG_USER=${SOURCE_PG_USER:-operator}
        read -p "Source PG Password: " -s SOURCE_PG_PASS
        echo
        read -p "Source PG Port [2285]: " SOURCE_PG_PORT
        SOURCE_PG_PORT=${SOURCE_PG_PORT:-2285}
        read -p "Source PG DB Name [postgres]: " SOURCE_PG_DBNAME
        SOURCE_PG_DBNAME=${SOURCE_PG_DBNAME:-postgres}
        read -p "Source PG Schema [control_panel]: " SOURCE_PG_SCHEMA
        SOURCE_PG_SCHEMA=${SOURCE_PG_SCHEMA:-control_panel}
        export SUDO_PASS SOURCE_PG_CONTAINER SOURCE_PG_HOST SOURCE_PG_USER SOURCE_PG_PASS SOURCE_PG_PORT SOURCE_PG_DBNAME SOURCE_PG_SCHEMA
    fi
}

function gather_dest_transfer_vars {
    if [ -z "$DEST_IP" ]; then
        clear
        print_prompt "--- Step 2/3: Destination Server & Installer Details ---"
        read -p "Destination IP Address: " DEST_IP
        read -p "Destination Username [support]: " DEST_USER
        DEST_USER=${DEST_USER:-support}
        read -p "Destination SSH Password: " -s DEST_PASS
        echo
        read -p "Destination Sudo Password (if different, else leave blank): " -s DEST_SUDO_PASS
        echo
        DEST_SUDO_PASS=${DEST_SUDO_PASS:-$DEST_PASS}
        
        print_prompt "--- Installer Options ---"
        read -p "Installer Version (e.g., 3.4.0-funcrel): " INSTALLER_VER
        read -p "Extend API Key: " API_KEY
        export DEST_IP DEST_USER DEST_PASS DEST_SUDO_PASS INSTALLER_VER API_KEY
    fi
}

function gather_dest_finalize_vars {
    if [ -z "$DEST_PG_CONTAINER" ]; then
        clear
        print_prompt "--- Step 4: Destination PostgreSQL Details ---"
        print_info "Before proceeding, please SSH to the destination server and run 'docker ps'"
        print_info "to find the new PostgreSQL container ID."
        echo
        read -p "Destination PG Container ID: " DEST_PG_CONTAINER
        read -p "Destination PG User [operator]: " DEST_PG_USER
        DEST_PG_USER=${DEST_PG_USER:-operator}
        read -p "Destination PG Password: " -s DEST_PG_PASS
        echo
        read -p "Destination PG Port [2285]: " DEST_PG_PORT
        DEST_PG_PORT=${DEST_PG_PORT:-2285}
        read -p "Destination PG DB Name [postgres]: " DEST_PG_DBNAME
        DEST_PG_DBNAME=${DEST_PG_DBNAME:-postgres}
        read -p "Destination PG Schema [control_panel]: " DEST_PG_SCHEMA
        DEST_PG_SCHEMA=${DEST_PG_SCHEMA:-control_panel}
        export DEST_PG_CONTAINER DEST_PG_USER DEST_PG_PASS DEST_PG_PORT DEST_PG_DBNAME DEST_PG_SCHEMA
    fi
}

# --- Main Logic Functions ---
function run_backup {
    clear
    print_info "======================================================"
    print_info "== STEP 1: RUNNING BACKUP ON SOURCE SERVER..."
    print_info "======================================================"
    
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    LOCAL_BACKUP_PATH="/home/$USER/cast_backup_$TIMESTAMP"

    print_info "[1/3] Creating local backup directory: $LOCAL_BACKUP_PATH"
    mkdir -p "$LOCAL_BACKUP_PATH" || { print_error "Failed to create directory."; return 1; }
    
    print_info "[2/3] Creating tarball of /opt/cast..."
    echo "$SUDO_PASS" | sudo -S tar -czvf "$LOCAL_BACKUP_PATH/opt_cast_backup.tar.gz" /opt/cast || { print_error "Failed to create tarball."; return 1; }

    print_info "[3/3] Dumping PostgreSQL database..."
    docker exec -e PGPASSWORD="$SOURCE_PG_PASS" "$SOURCE_PG_CONTAINER" bash -c "pg_dump -U '$SOURCE_PG_USER' -h '$SOURCE_PG_HOST' -p '$SOURCE_PG_PORT' -d '$SOURCE_PG_DBNAME' --schema='$SOURCE_PG_SCHEMA' -F c" > "$LOCAL_BACKUP_PATH/control_panel_schema.backup" || { print_error "Failed to dump database."; return 1; }

    print_success "BACKUP SUCCEEDED. Local backup path is: $LOCAL_BACKUP_PATH"
    export LOCAL_BACKUP_PATH
    STEP1_COMPLETE=true
}

function run_transfer {
    clear
    print_info "======================================================"
    print_info "== STEP 2: TRANSFERRING BACKUP TO DESTINATION..."
    print_info "======================================================"
    
    DEST_HOME_DIR="/home/$DEST_USER"
    print_info "Uploading backup from $LOCAL_BACKUP_PATH to $DEST_IP:$DEST_HOME_DIR"
    sshpass -p "$DEST_PASS" scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -r "$LOCAL_BACKUP_PATH" "$DEST_USER@$DEST_IP:$DEST_HOME_DIR/" || { print_error "Failed to transfer backup."; return 1; }

    BACKUP_BASENAME=$(basename "$LOCAL_BACKUP_PATH")
    export REMOTE_RESTORE_PATH="$DEST_HOME_DIR/$BACKUP_BASENAME"
    
    print_success "TRANSFER SUCCEEDED. Backup is now at $REMOTE_RESTORE_PATH"
    STEP2_COMPLETE=true
}

function run_restore_files {
    clear
    print_info "======================================================"
    print_info "== STEP 3: RESTORING FILES & INFRASTRUCTURE..."
    print_info "======================================================"

    sshpass -p "$DEST_PASS" ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "$DEST_USER@$DEST_IP" bash -s -- \
        "$REMOTE_RESTORE_PATH" "$DEST_IP" "$DEST_USER" "$DEST_SUDO_PASS" "$INSTALLER_VER" "$API_KEY" << 'EOF'
    set -e
    C_RESET='\033[0m'; C_GREEN='\033[0;32m'; C_RED='\033[0;31m'; C_CYAN='\033[0;36m'
    function print_info { echo -e "${C_CYAN}[REMOTE INFO] $1${C_RESET}"; }
    REMOTE_RESTORE_PATH="$1"; DEST_IP="$2"; DEST_USER="$3"; DEST_SUDO_PASS="$4"; INSTALLER_VER="$5"; API_KEY="$6"
    
    print_info "--- Preparing destination environment ---"

    print_info "[1/10] Pruning unused Docker networks..."
    echo "$DEST_SUDO_PASS" | sudo -S docker network prune -f

    print_info "[2/10] Pruning unused Docker volumes..."
    echo "$DEST_SUDO_PASS" | sudo -S docker volume prune -f
    
    TAR_FILE="$REMOTE_RESTORE_PATH/opt_cast_backup.tar.gz"
    print_info "[3/10] Downloading Installer..."; cd "$REMOTE_RESTORE_PATH"; if [ ! -f *.zip ]; then curl -# -O -J "https://extend.castsoftware.com/api/package/download/com.castsoftware.imaging.all.docker/$INSTALLER_VER?platform=linux_x64" -H "x-nuget-apikey: $API_KEY" -H "accept: application/octet-stream"; else echo "Installer exists."; fi
    print_info "[4/10] Extracting /opt/cast..."; mkdir -p "$REMOTE_RESTORE_PATH/temp_extract"; tar -xzf "$TAR_FILE" -C "$REMOTE_RESTORE_PATH/temp_extract"
    print_info "[5/10] Syncing files to /opt..."; echo "$DEST_SUDO_PASS" | sudo -S rsync -av --delete "$REMOTE_RESTORE_PATH/temp_extract/opt/" /opt/
    print_info "[6/10] Correcting ownership..."; echo "$DEST_SUDO_PASS" | sudo -S chown -R "$DEST_USER:$DEST_USER" /opt/cast
    print_info "[7/10] Updating .env files..."; for d in /opt/cast/installation/*; do if [ -f "$d/.env" ]; then sed -i "s/^HOST_HOSTNAME=.*/HOST_HOSTNAME=$DEST_IP/" "$d/.env"; fi; done
    print_info "[8/10] Pulling Docker images..."; for d in /opt/cast/installation/*; do if [ -f "$d/docker-compose.yml" ]; then print_info "  - Pulling for $(basename "$d")..."; (cd "$d" && docker compose pull); fi; done
    print_info "[9/10] Starting PostgreSQL service..."; (cd /opt/cast/installation/imaging-services && docker compose up -d)
    print_info "  - Waiting 20 seconds..."; sleep 20
    print_info "[10/10] Stopping non-PG services..."; (cd /opt/cast/installation/imaging-services && docker compose stop keycloak eureka-server); rm -rf "$REMOTE_RESTORE_PATH/temp_extract"
EOF
    if [ $? -ne 0 ]; then print_error "Restore Files script failed on the destination server."; return 1; fi
    
    print_success "RESTORE FILES & INFRASTRUCTURE SUCCEEDED."
    print_info "IMPORTANT: Please log in to the destination server now, run 'docker ps',"
    print_info "find the PostgreSQL Container ID, and proceed to Step 4."
    STEP3_COMPLETE=true
}

function run_restore_db {
    clear
    print_info "======================================================"
    print_info "== STEP 4: RESTORING DATABASE & FINALIZING..."
    print_info "======================================================"

    sshpass -p "$DEST_PASS" ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "$DEST_USER@$DEST_IP" bash -s -- \
        "$REMOTE_RESTORE_PATH" "$DEST_IP" "$DEST_PG_CONTAINER" "$DEST_PG_USER" "$DEST_PG_PASS" "$DEST_PG_PORT" "$DEST_PG_DBNAME" "$DEST_PG_SCHEMA" << 'EOF'
    set -e
    C_RESET='\033[0m'; C_GREEN='\033[0;32m'; C_RED='\033[0;31m'; C_CYAN='\033[0;36m'
    function print_info { echo -e "${C_CYAN}[REMOTE INFO] $1${C_RESET}"; }
    REMOTE_RESTORE_PATH="$1"; DEST_IP="$2"; DEST_PG_CONTAINER="$3"; DEST_PG_USER="$4"; DEST_PG_PASS="$5"; DEST_PG_PORT="$6"; DEST_PG_DBNAME="$7"; DEST_PG_SCHEMA="$8"
    PG_BACKUP_FILE="$REMOTE_RESTORE_PATH/control_panel_schema.backup"
    print_info "[1/5] Restoring database schema..."; cat "$PG_BACKUP_FILE" | docker exec -i -e PGPASSWORD="$DEST_PG_PASS" "$DEST_PG_CONTAINER" bash -c "pg_restore -U '$DEST_PG_USER' -h localhost -p 5432 -d '$DEST_PG_DBNAME' --clean"
    print_info "[2/5] Updating database properties..."; docker exec -e PGPASSWORD="$DEST_PG_PASS" "$DEST_PG_CONTAINER" psql -U "$DEST_PG_USER" -d "$DEST_PG_DBNAME" -c "UPDATE $DEST_PG_SCHEMA.properties SET value = 'http://$DEST_IP:8090' WHERE prop_key = 'keycloak.uri'; UPDATE $DEST_PG_SCHEMA.properties SET value = '$DEST_IP' WHERE prop_key = 'eureka.host'; UPDATE $DEST_PG_SCHEMA.properties SET value = 'jdbc:postgresql://$DEST_IP:$DEST_PG_PORT/$DEST_PG_DBNAME?currentSchema=$DEST_PG_SCHEMA' WHERE prop_key = 'spring.datasource.url';"
    print_info "[3/5] Updating ETL configuration..."; INSTALLER_ZIP=$(ls -1 "$REMOTE_RESTORE_PATH"/*.zip | head -n 1); unzip -o "$INSTALLER_ZIP" -d "$REMOTE_RESTORE_PATH/unzipped_installer"; (cd "$REMOTE_RESTORE_PATH/unzipped_installer/cast-imaging-viewer" && chmod +x imagingsetup && ./imagingsetup -hn "$DEST_IP" -ch "$DEST_IP" -cp "8098" -d "/opt/cast/installation/imaging-viewer" -ofl -u update)
    print_info "[4/5] Starting all services..."; for d in /opt/cast/installation/*; do if [ -f "$d/docker-compose.yml" ]; then print_info "  - Starting $(basename "$d")..."; (cd "$d" && docker compose up -d); fi; done
    print_info "[5/5] Final cleanup..."; rm -rf "$REMOTE_RESTORE_PATH/unzipped_installer"
EOF
    if [ $? -ne 0 ]; then print_error "Finalize script failed on the destination server."; return 1; fi

    print_success "DATABASE RESTORE & FINALIZE SUCCEEDED."
    print_success "The application should now be running on the destination server."
    STEP4_COMPLETE=true
}

# --- SCRIPT EXECUTION ---
function main_menu {
    while true; do
        clear
        echo "======================================================================"
        echo "         CAST Imaging Backup & Restore Utility (Linux CLI)"
        echo "======================================================================"
        print_info "Status:"
        [[ "$STEP1_COMPLETE" == true ]] && print_success "  Step 1 (Backup)   : COMPLETED - Path: $LOCAL_BACKUP_PATH" || echo "  Step 1 (Backup)   : PENDING"
        [[ "$STEP2_COMPLETE" == true ]] && print_success "  Step 2 (Transfer) : COMPLETED - Path: $REMOTE_RESTORE_PATH" || echo "  Step 2 (Transfer) : PENDING"
        [[ "$STEP3_COMPLETE" == true ]] && print_success "  Step 3 (Restore)  : COMPLETED" || echo "  Step 3 (Restore)  : PENDING"
        [[ "$STEP4_COMPLETE" == true ]] && print_success "  Step 4 (Finalize) : COMPLETED" || echo "  Step 4 (Finalize) : PENDING"
        echo "----------------------------------------------------------------------"
        echo "Please select an operation:"
        echo
        echo "  [1] Run Step 1: Backup"
        echo "  [2] Run Step 2: Transfer Backup to Destination"
        echo "  [3] Run Step 3: Restore Files & Infrastructure"
        echo "  [4] Run Step 4: Restore Database & Finalize"
        echo "  [5] Exit"
        echo
        read -p "Enter your choice [1-5]: " CHOICE

        case $CHOICE in
            1)
                gather_source_vars && run_backup
                press_enter_to_continue
                ;;