import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import os
from datetime import datetime
import time
import re

try:
    import paramiko
except ImportError:
    messagebox.showerror("Dependency Missing", "The 'paramiko' library is not installed.\nPlease run: pip install paramiko")
    exit()

try:
    from ttkthemes import ThemedTk
except ImportError:
    messagebox.showerror("Dependency Missing", "The 'ttkthemes' library is not installed.\nPlease run: pip install ttkthemes")
    exit()

# --- THEME COLORS ---

DARK_BACKGROUND = "#383838"
DARK_FOREGROUND = "#E0E0E0"
TEXT_BACKGROUND = "#2E2E2E"
CURSOR_COLOR = "white"

# --- ScrollableFrame Class ---

class ScrollableFrame(ttk.Frame):
    """A pure Tkinter scrollable frame that actually works!"""
    def __init__(self, container, *args, **kwargs):
        super().__init__(container, *args, **kwargs)
        canvas = tk.Canvas(self, bg=DARK_BACKGROUND, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.scrollable_frame = ttk.Frame(canvas)
        self.scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

# --- SSH Remote Client Class ---

class RemoteClient:
    """A wrapper for Paramiko that uses provided passwords for sudo."""
    def __init__(self, host, user, ssh_password, sudo_password, log_callback):
        self.host = host
        self.user = user
        self.ssh_password = ssh_password
        self.sudo_password = sudo_password if sudo_password else ssh_password
        self.log_callback = log_callback
        self.ssh = None
        try:
            self.ssh = paramiko.SSHClient()
            self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.log_callback(f"Connecting to {self.host}...\n")
            self.ssh.connect(hostname=host, username=user, password=ssh_password, timeout=10)
            self.log_callback(f"Connection to {self.host} successful.\n")
        except Exception as e:
            self.log_callback(f"ERROR: Connection to {self.host} failed: {e}\n")
            raise

    def exec_command(self, command, is_sudo=False, working_dir=None):
        """Executes a command, streams output, and returns a tuple (success_bool, full_output_str)."""
        full_command = command
        if working_dir:
            full_command = f"cd {working_dir} && {command}"
        if is_sudo:
            full_command = f"echo '{self.sudo_password}' | sudo -S -p '' {full_command}"

        self.log_callback(f"EXEC [{self.host}]: {command}\n")
        stdin, stdout, stderr = self.ssh.exec_command(full_command, get_pty=True)
        
        output_lines = []
        for line in iter(stdout.readline, ""):
            self.log_callback(line)
            output_lines.append(line)
        
        full_output = "".join(output_lines)
        exit_status = stdout.channel.recv_exit_status()

        if exit_status == 0:
            self.log_callback(f"SUCCESS: Command finished on {self.host}.\n\n")
            return (True, full_output.strip())
        else:
            error_output = "".join(stderr.readlines())
            log_err = error_output if error_output else full_output
            self.log_callback(f"ERROR: Command exited with status {exit_status}\n")
            if error_output:
                self.log_callback(f"Stderr: {error_output}\n")
            return (False, log_err.strip())

    def close(self):
        if self.ssh: self.ssh.close()
        self.log_callback(f"Connection to {self.host} closed.\n")

# --- Database Properties Editor Window ---

class DbEditorWindow(tk.Toplevel):
    def __init__(self, parent, client, db_config, new_ip):
        super().__init__(parent)
        self.transient(parent)
        self.title("Edit Database Properties")
        self.client = client
        self.db_config = db_config
        self.new_ip = new_ip
        self.properties = {}
        self.result = False

        self.grab_set()
        self.geometry("800x600")
        self.configure(bg=DARK_BACKGROUND)

        try:
            self.log = client.log_callback
            self.properties = self._fetch_properties()
            self._build_ui()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to fetch DB properties: {e}", parent=self)
            self.destroy()

    def _psql_exec(self, psql_command):
        """Helper to run a psql command inside the container."""
        pg_pass = self.db_config['pass']
        env_flag = f"-e PGPASSWORD='{pg_pass}'" if pg_pass else ""
        container = self.db_config['container']
        user, host, port, dbname = self.db_config['user'], self.db_config['host'], self.db_config['port'], self.db_config['dbname']
        
        psql_command = psql_command.replace("'", "'\\''")

        full_command = f"docker exec {env_flag} {container} psql -U {user} -h {host} -p {port} -d {dbname} -c '{psql_command}'"
        success, output = self.client.exec_command(full_command)
        if not success:
            raise Exception(f"psql command failed:\n{output}")
        return output

    def _fetch_properties(self):
        self.log("Fetching properties from database...\n")
        schema = self.db_config['schema']
        cmd = f"SELECT prop_key, value FROM {schema}.properties ORDER BY prop_key;"
        output = self._psql_exec(cmd)
        
        properties = {}
        lines = [line.strip() for line in output.split('\n') if '|' in line]
        for line in lines[1:-1]:
            parts = [p.strip() for p in line.split('|')]
            if len(parts) == 2:
                key, value = parts
                properties[key] = value
        
        if not properties:
            raise Exception("No properties found in database.")
        
        self.log("Properties fetched successfully.\n")
        return properties

    def _build_ui(self):
        main_frame = ttk.Frame(self, padding=10)
        main_frame.pack(expand=True, fill='both')
        ttk.Label(main_frame, text=f"Review and update properties for destination IP: {self.new_ip}", font=('Helvetica', 12, 'bold')).pack(pady=5)
        scroll_frame = ScrollableFrame(main_frame)
        scroll_frame.pack(expand=True, fill='both', pady=5)
        self.entries = {}
        grid = scroll_frame.scrollable_frame
        ttk.Label(grid, text="Property Key", font=('Helvetica', 10, 'bold')).grid(row=0, column=0, padx=5, pady=2, sticky='w')
        ttk.Label(grid, text="Property Value", font=('Helvetica', 10, 'bold')).grid(row=0, column=1, padx=5, pady=2, sticky='w')

        for i, (key, value) in enumerate(self.properties.items(), 1):
            ttk.Label(grid, text=key).grid(row=i, column=0, padx=5, pady=2, sticky='w')
            if key == "keycloak.uri": suggested_value = f"http://{self.new_ip}:8090"
            elif key == "eureka.host": suggested_value = self.new_ip
            elif key == "spring.datasource.url": suggested_value = f"jdbc:postgresql://{self.new_ip}:{self.db_config['port']}/{self.db_config['dbname']}?currentSchema={self.db_config['schema']}"
            else: suggested_value = value
            entry_var = tk.StringVar(value=suggested_value)
            entry = ttk.Entry(grid, textvariable=entry_var, width=80)
            entry.grid(row=i, column=1, padx=5, pady=2, sticky='ew')
            self.entries[key] = entry_var
            
        grid.columnconfigure(1, weight=1)
        self.save_button = ttk.Button(main_frame, text="Save and Continue", command=self.save_and_continue, style='Accent.TButton')
        self.save_button.pack(pady=10, ipady=5)

    def save_and_continue(self):
        self.save_button.config(state='disabled')
        try:
            self.log("Updating database properties...\n")
            schema = self.db_config['schema']
            for key, var in self.entries.items():
                new_value = var.get()
                if new_value != self.properties.get(key):
                    self.log(f"  Updating {key}...\n")
                    safe_value = new_value.replace("'", "''")
                    cmd = f"UPDATE {schema}.properties SET value = '{safe_value}' WHERE prop_key = '{key}';"
                    self._psql_exec(cmd)
            self.log("Database properties updated successfully.\n")
            self.result = True
            self.destroy()
        except Exception as e:
            messagebox.showerror("Save Error", f"Failed to save properties to DB: {e}", parent=self)
            self.save_button.config(state='normal')

# --- Main Application ---

class CASTBackupRestoreApp:
    def __init__(self, root):
        self.root = root
        self.root.title("CAST Imaging Backup & Restore Utility")
        self.root.geometry("1200x950")
        self.root.configure(bg=DARK_BACKGROUND)
        self.last_backup_path = None
        self.transfer_complete = False
        self.restore_step1_complete = False

        paned_window = ttk.PanedWindow(root, orient='horizontal')
        paned_window.pack(expand=True, fill='both', padx=10, pady=10)
        config_pane = ttk.Frame(paned_window, padding=5)
        paned_window.add(config_pane, weight=1)
        log_pane_container = ttk.Frame(paned_window)
        paned_window.add(log_pane_container, weight=2)
        scrollable_container = ScrollableFrame(config_pane)
        scrollable_container.pack(fill="both", expand=True)
        config_frame = scrollable_container.scrollable_frame
        
        self.create_source_config(config_frame)
        self.create_dest_config(config_frame)
        self.create_final_restore_action(config_frame)
        
        log_pane = ttk.LabelFrame(log_pane_container, text="Logs")
        log_pane.pack(expand=True, fill='both', padx=5, pady=0)
        self.log_widget = scrolledtext.ScrolledText(
            log_pane, wrap='word', state='disabled', bg=TEXT_BACKGROUND, fg=DARK_FOREGROUND,
            insertbackground=CURSOR_COLOR, relief='flat', borderwidth=1
        )
        self.log_widget.pack(expand=True, fill='both', padx=5, pady=5)

    def _create_common_pg_widgets(self, parent_frame, container_var, host_var, port_var, db_var, schema_var, user_var, pass_var, is_destination=False):
        ttk.Label(parent_frame, text="PostgreSQL Container ID:").grid(row=0, column=0, sticky='w', pady=2)
        ttk.Entry(parent_frame, textvariable=container_var).grid(row=0, column=1, sticky='ew')
        ttk.Label(parent_frame, text="DB Host (FQDN/IP Address):").grid(row=1, column=0, sticky='w', pady=2)
        ttk.Entry(parent_frame, textvariable=host_var).grid(row=1, column=1, sticky='ew')
        ttk.Label(parent_frame, text="DB Port:").grid(row=2, column=0, sticky='w', pady=2)
        ttk.Entry(parent_frame, textvariable=port_var).grid(row=2, column=1, sticky='ew')
        ttk.Label(parent_frame, text="DB Name:").grid(row=3, column=0, sticky='w', pady=2)
        ttk.Entry(parent_frame, textvariable=db_var).grid(row=3, column=1, sticky='ew')
        ttk.Label(parent_frame, text="DB Schema:").grid(row=4, column=0, sticky='w', pady=2)
        ttk.Entry(parent_frame, textvariable=schema_var).grid(row=4, column=1, sticky='ew')
        ttk.Label(parent_frame, text="DB User:").grid(row=5, column=0, sticky='w', pady=2)
        ttk.Entry(parent_frame, textvariable=user_var).grid(row=5, column=1, sticky='ew')
        ttk.Label(parent_frame, text="DB Password:").grid(row=6, column=0, sticky='w', pady=2)
        ttk.Entry(parent_frame, textvariable=pass_var, show="*").grid(row=6, column=1, sticky='ew')
        parent_frame.grid_columnconfigure(1, weight=1)

        if is_destination:
            note_label = ttk.Label(parent_frame, 
                                   text="Note: Run 'docker ps' on the destination VM to find the PostgreSQL Container ID.",
                                   font=('Helvetica', 8, 'italic'),
                                   wraplength=350)
            note_label.grid(row=7, column=0, columnspan=2, sticky='w', pady=(8,0), padx=2)


    def create_source_config(self, parent):
        frame = ttk.LabelFrame(parent, text="Source Configuration", padding=10)
        frame.pack(padx=10, pady=5, fill='x', expand=True)
        ttk.Label(frame, text="Linux VM Details", font=('Helvetica', 10, 'bold')).pack(anchor='w', pady=(0,5))
        vm_frame = ttk.Frame(frame, padding=5)
        vm_frame.pack(fill='x', expand=True, padx=5)
        ttk.Label(vm_frame, text="IP Address:").grid(row=0, column=0, sticky='w', pady=2)
        self.source_ip = tk.StringVar(value="")
        ttk.Entry(vm_frame, textvariable=self.source_ip).grid(row=0, column=1, sticky='ew')
        ttk.Label(vm_frame, text="Username:").grid(row=1, column=0, sticky='w', pady=2)
        self.source_user = tk.StringVar(value="support")
        ttk.Entry(vm_frame, textvariable=self.source_user).grid(row=1, column=1, sticky='ew')
        ttk.Label(vm_frame, text="SSH Password:").grid(row=2, column=0, sticky='w', pady=2)
        self.source_pass = tk.StringVar()
        ttk.Entry(vm_frame, textvariable=self.source_pass, show="*").grid(row=2, column=1, sticky='ew')
        ttk.Label(vm_frame, text="Sudo Password:").grid(row=3, column=0, sticky='w', pady=2)
        self.source_sudo_pass = tk.StringVar()
        ttk.Entry(vm_frame, textvariable=self.source_sudo_pass, show="*").grid(row=3, column=1, sticky='ew')
        vm_frame.grid_columnconfigure(1, weight=1)
        ttk.Separator(frame, orient='horizontal').pack(fill='x', pady=10)
        ttk.Label(frame, text="PostgreSQL Details", font=('Helvetica', 10, 'bold')).pack(anchor='w', pady=(0,5))
        pg_frame = ttk.Frame(frame, padding=5)
        pg_frame.pack(fill='x', expand=True, padx=5)
        self.source_pg_container = tk.StringVar(value="")
        self.source_pg_host = tk.StringVar(value="")
        self.source_pg_port = tk.StringVar(value="2285")
        self.source_pg_dbname = tk.StringVar(value="postgres")
        self.source_pg_schema = tk.StringVar(value="control_panel")
        self.source_pg_user = tk.StringVar(value="operator")
        self.source_pg_pass = tk.StringVar()
        self._create_common_pg_widgets(pg_frame, self.source_pg_container, self.source_pg_host, self.source_pg_port, self.source_pg_dbname, self.source_pg_schema, self.source_pg_user, self.source_pg_pass, is_destination=False)
        
        backup_frame = ttk.Frame(parent)
        backup_frame.pack(pady=(10, 5), padx=10, fill='x', expand=True)
        self.backup_button = ttk.Button(backup_frame, text="1. Run Backup", command=lambda: self.start_process('backup'), style='Accent.TButton')
        self.backup_button.pack(ipady=5, fill='x', expand=True)

    def create_dest_config(self, parent):
        frame = ttk.LabelFrame(parent, text="Destination Configuration", padding=10)
        frame.pack(padx=10, pady=5, fill='x', expand=True)
        ttk.Label(frame, text="Linux VM Details", font=('Helvetica', 10, 'bold')).pack(anchor='w', pady=(0,5))
        vm_frame = ttk.Frame(frame, padding=5)
        vm_frame.pack(fill='x', expand=True, padx=5)
        ttk.Label(vm_frame, text="IP Address:").grid(row=0, column=0, sticky='w', pady=2)
        self.dest_ip = tk.StringVar(value="")
        ttk.Entry(vm_frame, textvariable=self.dest_ip).grid(row=0, column=1, sticky='ew')
        ttk.Label(vm_frame, text="Username:").grid(row=1, column=0, sticky='w', pady=2)
        self.dest_user = tk.StringVar(value="support")
        ttk.Entry(vm_frame, textvariable=self.dest_user).grid(row=1, column=1, sticky='ew')
        ttk.Label(vm_frame, text="SSH Password:").grid(row=2, column=0, sticky='w', pady=2)
        self.dest_pass = tk.StringVar()
        ttk.Entry(vm_frame, textvariable=self.dest_pass, show="*").grid(row=2, column=1, sticky='ew')
        ttk.Label(vm_frame, text="Sudo Password:").grid(row=3, column=0, sticky='w', pady=2)
        self.dest_sudo_pass = tk.StringVar()
        ttk.Entry(vm_frame, textvariable=self.dest_sudo_pass, show="*").grid(row=3, column=1, sticky='ew')
        ttk.Label(vm_frame, text="Remote Backup Path:").grid(row=4, column=0, sticky='w', pady=(10,0))
        self.remote_restore_path = tk.StringVar(value="/home/support/")
        ttk.Entry(vm_frame, textvariable=self.remote_restore_path).grid(row=4, column=1, sticky='ew', pady=(10,0))
        vm_frame.grid_columnconfigure(1, weight=1)
        ttk.Separator(frame, orient='horizontal').pack(fill='x', pady=10)
        ttk.Label(frame, text="Installer Options", font=('Helvetica', 10, 'bold')).pack(anchor='w', pady=(0,5))
        installer_frame = ttk.Frame(frame, padding=5)
        installer_frame.pack(fill='x', expand=True, padx=5)
        self.download_installer_var = tk.BooleanVar(value=True)
        cb_download = ttk.Checkbutton(installer_frame, text="Download CAST Imaging Installer on Destination", variable=self.download_installer_var, command=self.toggle_download_options)
        cb_download.grid(row=0, column=0, columnspan=2, sticky='w', pady=(0,5))
        ttk.Label(installer_frame, text="Console Imaging V3 Version:").grid(row=1, column=0, sticky='w')
        self.installer_version = tk.StringVar(value="")
        self.version_entry = ttk.Entry(installer_frame, textvariable=self.installer_version)
        self.version_entry.grid(row=1, column=1, sticky='ew', padx=5)
        ttk.Label(installer_frame, text="Extend API Key:").grid(row=2, column=0, sticky='w')
        self.api_key = tk.StringVar(value="")
        self.apikey_entry = ttk.Entry(installer_frame, textvariable=self.api_key, show="*")
        self.apikey_entry.grid(row=2, column=1, sticky='ew', padx=5)
        installer_frame.grid_columnconfigure(1, weight=1)
        self.toggle_download_options()

        # --- Moved Restore Actions (2 & 3) ---
        restore_frame_1 = ttk.Frame(frame)
        restore_frame_1.pack(pady=(15, 5), padx=5, fill='x', expand=True)
        self.transfer_button = ttk.Button(restore_frame_1, text="2. Transfer Backup to Destination", command=lambda: self.start_process('transfer'), state='disabled')
        self.transfer_button.pack(ipady=5, fill='x', expand=True)
        self.restore_files_button = ttk.Button(restore_frame_1, text="3. Restore Files & Infrastructure", command=lambda: self.start_process('restore_step1'), state='disabled')
        self.restore_files_button.pack(ipady=5, fill='x', expand=True, pady=(5,0))

        ttk.Separator(frame, orient='horizontal').pack(fill='x', pady=10)
        ttk.Label(frame, text="PostgreSQL Details", font=('Helvetica', 10, 'bold')).pack(anchor='w', pady=(0,5))
        pg_frame = ttk.Frame(frame, padding=5)
        pg_frame.pack(fill='x', expand=True, padx=5)
        self.dest_pg_container = tk.StringVar(value="")
        self.dest_pg_host = tk.StringVar(value="")
        self.dest_pg_port = tk.StringVar(value="2285")
        self.dest_pg_dbname = tk.StringVar(value="postgres")
        self.dest_pg_schema = tk.StringVar(value="control_panel")
        self.dest_pg_user = tk.StringVar(value="operator")
        self.dest_pg_pass = tk.StringVar()
        self._create_common_pg_widgets(pg_frame, self.dest_pg_container, self.dest_pg_host, self.dest_pg_port, self.dest_pg_dbname, self.dest_pg_schema, self.dest_pg_user, self.dest_pg_pass, is_destination=True)

    def create_final_restore_action(self, parent):
        action_frame = ttk.LabelFrame(parent, text="Finalize", padding=10)
        action_frame.pack(padx=10, pady=10, fill='x', expand=True)
        self.restore_db_button = ttk.Button(action_frame, text="4. Restore Database & Finalize", command=lambda: self.start_process('restore_step2'), state='disabled')
        self.restore_db_button.pack(ipady=5, fill='x', expand=True)

    def toggle_download_options(self):
        state = 'normal' if self.download_installer_var.get() else 'disabled'
        self.version_entry.config(state=state)
        self.apikey_entry.config(state=state)

    def log(self, message):
        self.root.after(0, lambda: self._log_callback(message))

    def _log_callback(self, message):
        self.log_widget.configure(state='normal'); self.log_widget.insert(tk.END, message); self.log_widget.configure(state='disabled'); self.log_widget.see(tk.END)

    def _execute_and_check(self, client: RemoteClient, command: str, is_sudo=False, working_dir=None):
        success, output = client.exec_command(command, is_sudo, working_dir)
        if not success:
            raise Exception(f"Failed to execute remote command: {command}\nError: {output}")
        return output
    
    def _ensure_package_installed(self, client: RemoteClient, package_name: str):
        self.log(f"--- Checking for {package_name} on {client.host} ---\n")
        success, _ = client.exec_command(f"command -v {package_name}")
        if success:
            self.log(f"{package_name} is already installed on {client.host}.\n")
            return
        self.log(f"{package_name} not found on {client.host}. Attempting automated installation...\n")
        if client.exec_command("command -v dnf")[0]: self._execute_and_check(client, f"dnf install -y {package_name}", is_sudo=True)
        elif client.exec_command("command -v yum")[0]: self._execute_and_check(client, f"yum install -y {package_name}", is_sudo=True)
        elif client.exec_command("command -v apt-get")[0]:
            self._execute_and_check(client, "apt-get update -y", is_sudo=True)
            self._execute_and_check(client, f"apt-get install -y {package_name}", is_sudo=True)
        else: raise Exception(f"Could not find a supported package manager on {client.host} to install {package_name}.")
        self.log(f"{package_name} installed successfully.\n")

    def _set_all_buttons_state(self, state):
        self.backup_button.config(state=state)
        self.transfer_button.config(state=state)
        self.restore_files_button.config(state=state)
        self.restore_db_button.config(state=state)

    def _update_button_states(self):
        self.backup_button.config(state='normal')
        self.transfer_button.config(state='normal' if self.last_backup_path else 'disabled')
        self.restore_files_button.config(state='normal' if self.transfer_complete else 'disabled')
        self.restore_db_button.config(state='normal' if self.restore_step1_complete else 'disabled')

    def start_process(self, mode):
        self.log_widget.configure(state='normal'); self.log_widget.delete(1.0, tk.END); self.log_widget.configure(state='disabled')
        target_func = None
        try:
            if mode == 'backup':
                if not all([self.source_ip.get(), self.source_user.get(), self.source_pass.get(), self.source_pg_container.get()]): raise ValueError("Source VM details (IP, User, Pass) and PG Container Name are required.")
                target_func = self.run_backup
            elif mode == 'transfer':
                if not all([self.source_ip.get(), self.source_user.get(), self.source_pass.get(), self.dest_ip.get(), self.dest_user.get(), self.dest_pass.get()]): raise ValueError("Both Source and Destination VM details are required for transfer.")
                if not self.last_backup_path: raise ValueError("No successful backup found to transfer. Please run a backup first.")
                target_func = self.run_transfer
            elif mode == 'restore_step1':
                if not all([self.dest_ip.get(), self.dest_user.get(), self.dest_pass.get(), self.remote_restore_path.get()]): raise ValueError("Destination VM details and Remote Backup Path are required.")
                if self.download_installer_var.get() and not all([self.installer_version.get(), self.api_key.get()]): raise ValueError("Installer Version and API Key are required.")
                target_func = self.run_restore_step1_files
            elif mode == 'restore_step2':
                if not all([self.dest_ip.get(), self.dest_user.get(), self.dest_pass.get(), self.remote_restore_path.get(), self.dest_pg_container.get()]): raise ValueError("Destination VM details, Backup Path, and PG Container are required.")
                target_func = self.run_restore_step2_db
            
            if target_func:
                self._set_all_buttons_state('disabled')
                thread = threading.Thread(target=target_func, daemon=True); thread.start()
        except ValueError as e:
            messagebox.showerror("Input Error", str(e)); self.root.after(0, self._update_button_states)

    def run_backup(self):
        self.last_backup_path, self.transfer_complete, self.restore_step1_complete = None, False, False
        src_client = None
        try:
            self.log("--- Starting Backup Process ---\n")
            src_client = RemoteClient(self.source_ip.get(), self.source_user.get(), self.source_pass.get(), self.source_sudo_pass.get(), self.log)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_dir_name = f"cast_backup_{timestamp}"
            remote_backup_dir = f"/home/{self.source_user.get()}/{backup_dir_name}"
            self._execute_and_check(src_client, f"mkdir -p {remote_backup_dir}")
            self._execute_and_check(src_client, f"tar -czvf {remote_backup_dir}/opt_cast_backup.tar.gz /opt/cast", is_sudo=True)
            pg_container = self.source_pg_container.get()
            remote_pg_backup = f"{remote_backup_dir}/control_panel_schema.backup"
            pg_dump_options = (f"pg_dump -U {self.source_pg_user.get()} -h {self.source_pg_host.get()} -p {self.source_pg_port.get()} "
                               f"-d {self.source_pg_dbname.get()} --schema={self.source_pg_schema.get()} -F c")
            inner_command = f"cd /usr/bin && {pg_dump_options}"
            pg_pass = self.source_pg_pass.get()
            env_flag = f"-e PGPASSWORD='{pg_pass}'" if pg_pass else ""
            final_command = f"docker exec {env_flag} {pg_container} /bin/bash -c \"{inner_command}\" > {remote_pg_backup}"
            self._execute_and_check(src_client, final_command)
            self.last_backup_path = remote_backup_dir
            
            self.root.after(0, lambda: (
                self._update_button_states(),
                messagebox.showinfo("Backup Complete", f"Backup created successfully at:\n{remote_backup_dir}\nReady to Transfer.")
            ))
        except Exception as e:
            messagebox.showerror("Backup Failed", str(e)); self.root.after(0, self._update_button_states)
        finally:
            if src_client: src_client.close()

    def run_transfer(self):
        self.transfer_complete, self.restore_step1_complete = False, False
        src_client = None
        try:
            self.log("--- Starting Backup Transfer Process ---\n")
            src_client = RemoteClient(self.source_ip.get(), self.source_user.get(), self.source_pass.get(), self.source_sudo_pass.get(), self.log)
            self._ensure_package_installed(src_client, "sshpass")
            self.log("--- Securely copying files to destination ---\n")
            dest_ip, dest_user, dest_pass = self.dest_ip.get(), self.dest_user.get(), self.dest_pass.get()
            dest_home_dir = f"/home/{dest_user}"
            scp_command = f"sshpass -p '{dest_pass}' scp -r -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null {self.last_backup_path} {dest_user}@{dest_ip}:{dest_home_dir}/"
            self._execute_and_check(src_client, scp_command)
            backup_folder_name = os.path.basename(self.last_backup_path)
            new_remote_path = f"{dest_home_dir}/{backup_folder_name}"
            self.transfer_complete = True
            
            self.root.after(0, lambda: (
                self.remote_restore_path.set(new_remote_path),
                self._update_button_states(),
                messagebox.showinfo("Transfer Complete", "Backup transferred successfully.\n\nReady for Restore Step 3.")
            ))
        except Exception as e:
            messagebox.showerror("Transfer Failed", str(e)); self.root.after(0, self._update_button_states)
        finally:
            if src_client: src_client.close()
            
    def run_restore_step1_files(self):
        self.restore_step1_complete = False
        dest_client = None
        remote_backup_dir = self.remote_restore_path.get()
        try:
            self.log("--- Starting Restore (Step 1/2): Files & Infrastructure ---\n")
            dest_client = RemoteClient(self.dest_ip.get(), self.dest_user.get(), self.dest_pass.get(), self.dest_sudo_pass.get(), self.log)

            if self.download_installer_var.get():
                self.log("--- Checking for existing installer ZIP file... ---\n")
                check_cmd = f"find {remote_backup_dir} -maxdepth 1 -name '*.zip' -print -quit"
                zip_exists, existing_zip = dest_client.exec_command(check_cmd)
                
                if zip_exists and existing_zip.strip():
                    self.log(f"Found existing installer: {os.path.basename(existing_zip.strip())}. Skipping download.\n")
                else:
                    self.log("No existing installer found. Proceeding with download...\n")
                    version, api_key = self.installer_version.get(), self.api_key.get()
                    curl_cmd = f'curl -# -O -J "https://extend.castsoftware.com/api/package/download/com.castsoftware.imaging.all.docker/{version}?platform=linux_x64" -H "x-nuget-apikey: {api_key}" -H "accept: application/octet-stream"'
                    self._execute_and_check(dest_client, f"mkdir -p {remote_backup_dir}")
                    self._execute_and_check(dest_client, curl_cmd, working_dir=remote_backup_dir)
                    zip_exists_after_dl, _ = dest_client.exec_command(check_cmd)
                    if not zip_exists_after_dl: raise Exception("Installer download was selected but no .zip file was found after download. Check API Key and Version.")

            self.log("--- Preparing file restoration ---\n")
            file_list_str = self._execute_and_check(dest_client, f"ls -1 {remote_backup_dir}")
            file_list = [line.strip() for line in file_list_str.split('\n')]
            opt_backup_name = next((f for f in file_list if f.endswith('.tar.gz')), None)
            if not opt_backup_name: raise FileNotFoundError(f"Backup archive (*.tar.gz) not found in {remote_backup_dir}")
            
            self._ensure_package_installed(dest_client, "rsync")
            temp_extract_dir = f"{remote_backup_dir}/temp_extract"
            self.log(f"--- Extracting backup to temporary directory: {temp_extract_dir} ---\n")
            self._execute_and_check(dest_client, f"rm -rf {temp_extract_dir} && mkdir -p {temp_extract_dir}")
            self._execute_and_check(dest_client, f"tar -xzf {remote_backup_dir}/{opt_backup_name} -C {temp_extract_dir}")
            
            self.log("--- Synchronizing /opt with rsync ---\n")
            self._execute_and_check(dest_client, f"mkdir -p /opt", is_sudo=True)
            self._execute_and_check(dest_client, f"rsync -av --delete {temp_extract_dir}/opt/ /opt/", is_sudo=True)
            self._execute_and_check(dest_client, f"rm -rf {temp_extract_dir}")

            dest_user = self.dest_user.get()
            self.log(f"--- Correcting ownership of /opt/cast for user {dest_user} ---\n")
            self._execute_and_check(dest_client, f"chown -R {dest_user}:{dest_user} /opt/cast", is_sudo=True)
            
            install_dir = "/opt/cast/installation"
            new_ip = self.dest_ip.get()
            service_dirs = ["imaging-services", "imaging-node", "imaging-dashboards"]

            for service in service_dirs:
                self.log(f"--- Updating IP in {service}/.env file ---\n")
                service_path = f"{install_dir}/{service}"
                
                check_exists_cmd = f"[ -f .env ] && echo 'found' || echo 'not found'"
                success, output = dest_client.exec_command(check_exists_cmd, working_dir=service_path)
                
                if success and "found" in output:
                    self._execute_and_check(dest_client, f"sed -i 's/^HOST_HOSTNAME=.*/HOST_HOSTNAME={new_ip}/' .env", working_dir=service_path)
                else:
                    self.log(f"WARNING: .env file not found in {service_path}, skipping update for this service.\n")
            
            self.log("--- Pulling Docker images for each service ---\n")
            for service in service_dirs:
                service_path = f"{install_dir}/{service}"
                self.log(f"  - Pulling images for {service}...\n")
                check_compose_exists_cmd = f"[ -f docker-compose.yml ] && echo 'found' || echo 'not found'"
                success, output = dest_client.exec_command(check_compose_exists_cmd, working_dir=service_path)
                if success and "found" in output:
                    self._execute_and_check(dest_client, "docker compose pull", working_dir=service_path)
                else:
                    self.log(f"WARNING: docker-compose.yml not found in {service_path}, skipping pull.\n")

            imaging_services_path = f"{install_dir}/imaging-services"
            self.log("--- Starting imaging-services (for PostgreSQL) ---\n")
            self._execute_and_check(dest_client, "docker compose up -d", working_dir=imaging_services_path)
            
            self.log("  - Waiting 20 seconds for services to initialize...\n"); time.sleep(20)

            self.log("--- Stopping non-PostgreSQL services ---\n")
            services_to_stop_str = self._execute_and_check(dest_client, "docker compose ps --services | grep -v postgres", working_dir=imaging_services_path)
            if services_to_stop_str: self._execute_and_check(dest_client, f"docker compose stop {services_to_stop_str.replace(chr(13), '').replace('\n', ' ')}", working_dir=imaging_services_path)
            
            self.restore_step1_complete = True
            self.root.after(0, lambda: (
                self._update_button_states(),
                messagebox.showinfo("Restore Step 3 Complete", "Files and infrastructure restored successfully.\n\nReady for Restore Step 4.")
            ))
        except Exception as e:
            messagebox.showerror("Restore Step 3 Failed", str(e)); self.root.after(0, self._update_button_states)
        finally:
            if dest_client: dest_client.close()

    def run_restore_step2_db(self):
        dest_client = None
        remote_backup_dir = self.remote_restore_path.get()
        try:
            self.log("--- Starting Restore (Step 2/2): Database & Finalization ---\n")
            dest_client = RemoteClient(self.dest_ip.get(), self.dest_user.get(), self.dest_pass.get(), self.dest_sudo_pass.get(), self.log)
            file_list_str = self._execute_and_check(dest_client, f"ls -1 {remote_backup_dir}")
            file_list = [line.strip() for line in file_list_str.split('\n')]
            pg_backup_name = next((f for f in file_list if f.endswith('.backup')), None)
            installer_zip_name = next((f for f in file_list if f.endswith('.zip')), None)
            if not all([pg_backup_name, installer_zip_name]): raise FileNotFoundError(f"Required files (*.backup, *.zip) not found in {remote_backup_dir}")
            
            remote_pg_backup = f"{remote_backup_dir}/{pg_backup_name}"
            self.log("--- Restoring Database Schema into container ---\n")
            pg_container = self.dest_pg_container.get()
            pg_restore_options = (f"pg_restore -U {self.dest_pg_user.get()} -h {self.dest_pg_host.get()} -p {self.dest_pg_port.get()} "
                                  f"-d {self.dest_pg_dbname.get()} --clean")
            inner_command = f"cd /usr/bin && {pg_restore_options}"
            pg_pass = self.dest_pg_pass.get()
            env_flag = f"-e PGPASSWORD='{pg_pass}'" if pg_pass else ""
            final_command = f"cat {remote_pg_backup} | docker exec -i {env_flag} {pg_container} /bin/bash -c \"{inner_command}\""
            self._execute_and_check(dest_client, final_command)
            self.log("--- Opening Database Property Editor ---\n")
            db_config = { 'container': self.dest_pg_container.get(), 'user': self.dest_pg_user.get(), 'pass': self.dest_pg_pass.get(), 'host': self.dest_pg_host.get(), 'port': self.dest_pg_port.get(), 'dbname': self.dest_pg_dbname.get(), 'schema': self.dest_pg_schema.get() }
            editor = DbEditorWindow(self.root, dest_client, db_config, self.dest_ip.get())
            self.root.wait_window(editor)
            if not editor.result: raise Exception("Database property update was cancelled or failed.")
            
            self.log("--- Updating ETL Configuration ---\n")
            remote_installer_zip = f"{remote_backup_dir}/{installer_zip_name}"
            unzip_dest = f"{remote_backup_dir}/unzipped_installer"
            self._execute_and_check(dest_client, f"unzip -o {remote_installer_zip} -d {unzip_dest}")
            
            viewer_setup_dir = f"{unzip_dest}/cast-imaging-viewer"
            
            self.log(f"--- Making imagingsetup executable in {viewer_setup_dir} ---\n")
            self._execute_and_check(dest_client, "chmod +x imagingsetup", working_dir=viewer_setup_dir)
            
            install_dir = "/opt/cast/installation"
            new_ip = self.dest_ip.get()
            etl_cmd = f'./imagingsetup -hn "{new_ip}" -ch "{new_ip}" -cp "8098" -d "{install_dir}/imaging-viewer" -ofl -u update'
            self._execute_and_check(dest_client, etl_cmd, working_dir=viewer_setup_dir)
            
            self.log("--- Starting All Application Services ---\n")
            service_dirs = ["imaging-services", "imaging-node", "imaging-dashboards"]
            for service in service_dirs:
                service_path = f"{install_dir}/{service}"
                self.log(f"  - Starting {service}...\n")
                check_compose_exists_cmd = f"[ -f docker-compose.yml ] && echo 'found' || echo 'not found'"
                success, output = dest_client.exec_command(check_compose_exists_cmd, working_dir=service_path)
                if success and "found" in output:
                     self._execute_and_check(dest_client, "docker compose up -d", working_dir=service_path)
                else:
                    self.log(f"WARNING: docker-compose.yml not found in {service_path}, skipping start.\n")
            
            self._execute_and_check(dest_client, f"rm -rf {unzip_dest}")
            
            self.last_backup_path, self.transfer_complete, self.restore_step1_complete = None, False, False
            self.root.after(0, lambda: (
                self._update_button_states(),
                messagebox.showinfo("Restore Complete", "The CAST Imaging application has been successfully restored and started.")
            ))
        except Exception as e:
            messagebox.showerror("Restore Step 4 Failed", str(e)); self.root.after(0, self._update_button_states)
        finally:
            if dest_client: dest_client.close()

if __name__ == "__main__":
    root = ThemedTk(theme="equilux")
    style = ttk.Style(root)
    style.configure('Accent.TButton', font=('Helvetica', 10, 'bold'))
    app = CASTBackupRestoreApp(root)
    root.mainloop()