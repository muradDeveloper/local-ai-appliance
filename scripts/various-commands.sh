


## Create necessary directories for various services
 mkdir -p /mnt/ai-files/{traefik/{dynamic,acme},redis/data,postgres/{data,init},ollama/data,authentik/{media,templates,certs},open-webui/{data,knowledge},portainer/data}


## Restic is lightweight to install on Ubuntu:
sudo apt install restic


/mnt/user/tmp_share/backups/ai-backups

## install smbclient to enable restic to backup to a Windows share
apt install smbclient

## install cifs-utils to enable mounting a Windows share
apt install cifs-utils