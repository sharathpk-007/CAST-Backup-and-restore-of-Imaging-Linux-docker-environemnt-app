# Backup and Restore of Imaging Console

# V3 from One Linux VM to Another

Source VM: <Source FQDN/IP>
Destination VM: <Destination FQDN/IP>

**Backup Process**

1. Backup of /opt/cast Folder
To take a backup of the /opt/cast directory from the source VM:

```
sudo tar - czvf /home/support/opt_cast_backup_$(date +%Y%m%d).tar.gz /opt/cast
```
This will create a compressed archive of the entire CAST installation directory and store it
under /home/support.

2. Backup of Installer Package
Ensure you also back up the installer ZIP file:

```
/home/support/com.castsoftware.imaging.all.docker.3.4.0-funcrel.zip
```
```
This contains the Docker setup and application images.
```
3. PostgreSQL Dump Backup

To migrate the control_panel schema:

pg_dump - U operator - h <Source FQDN/IP> - p 2285 - d postgres --schema=control_panel -
F c -f /home/support/control_panel_schema_$(date +%Y%m%d).backup

To migrate all schemas, update:

- Take a full schema backup (or use pg_dumpall if needed),
- Update the following file on the destination:

cast-ms.connectionProfiles.pmx (replace <Source FQDN/IP> with <Destination
FQDN/IP>)


4. Transfer Backup Files to Destination VM
Use scp to securely copy files to the destination server:

scp /home/support/opt_cast_backup_20250730.tar.gz support@<Destination
FQDN/IP>:/home/support/

scp /home/support/com.castsoftware.imaging.all.docker.3.4.0-funcrel.zip
support@<Destination FQDN/IP>:/home/support/

scp /home/support/control_panel_schema_20250730.backup support@<Destination
FQDN/IP>:/home/support/

**Restore Process**

1. Install rsync on Destination VM
Install rsync to safely copy files while preserving structure and permissions:

```
sudo yum install rsync -y
```
2. Restore /opt/cast
Synchronize the contents of the backed-up /opt/cast directory:

```
sudo rsync -av /home/support/opt/ /opt/
```
3. Docker Image Setup
Navigate to:

```
cd /opt/cast/installation
```
Then pull the necessary images:

```
docker compose pull imaging-service
docker compose pull imaging-node
docker compose pull imaging-viewer
docker compose pull imaging-dashboard
```

4. Unzip Installer
Extract the zipped installer file:

```
cd /home/support
```
unzip com.castsoftware.imaging.all.docker.3.4.0-funcrel.zip - d
com.castsoftware.imaging.all.docker.3.4.0-funcrel

5. Update IPs in .env Files (replace with <Destination FQDN/IP>)
Update the .env files in the following containers with the new <Destination FQDN/IP>)
- imaging-service
- imaging-node
- imaging-dashboard

From /opt/cast/installation, run:

vi .env

Update and save each file accordingly. Example


6. Start Only imaging-service (for PostgreSQL)
From /opt/cast/installation, start only the imaging-service to initialize the PostgreSQL
container:

```
docker compose up - d imaging-service
```
Once all containers under imaging-service are up, stop all except the PostgreSQL container

7. Restore control_panel Schema
Use DBeaver, pgAdmin, or CLI to restore the schema to the destination VM PostgreSQL:

Host: <Destination FQDN/IP>
Port: 2285
User: operator

Update the properties table inside the schema with <Destination FQDN/IP>.


8. Update ETL Configuration
Navigate to:

```
cd /home/support/com.castsoftware.imaging.all.docker.3.4.0-funcrel/imaging-viewer
```
Run the setup script to update the control panel host and port in the ETL container:

Run the chmod +x cast-imaging-viewer/imagingsetup

And then run the below script

./imagingsetup - hn "<Destination FQDN/IP>" - ch "<Destination FQDN/IP>" - cp "8098" - d
"/opt/cast/installation/imaging-viewer" -ofl -u update

9. Start Remaining Containers
From /opt/cast/installation, start:

```
docker compose up - d imaging-service imaging-node imaging-dashboard
```
Conclusion
Imaging Console V3 has been successfully migrated from <Source FQDN/IP> to
<Destination FQDN/IP>.


