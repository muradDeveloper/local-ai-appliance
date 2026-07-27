


## Create necessary directories for various services
 mkdir -p /mnt/ai-files/{traefik/{dynamic,acme},redis/data,postgres/{data,init},ollama/data,authentik/{media,templates,certs},open-webui/{data,knowledge},portainer/data}
mkdir -p /mnt/ai-files/speaches/models

## Restic is lightweight to install on Ubuntu:
sudo apt install restic


/mnt/user/tmp_share/backups/ai-backups

## install smbclient to enable restic to backup to a Windows share
apt install smbclient

## install cifs-utils to enable mounting a Windows share
apt install cifs-utils

## Test Speaches TTS
curl -s http://localhost:8000/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{"model":"speaches-ai/Kokoro-82M-v1.0-ONNX","voice":"af_heart","input":"Warming up."}' \
  --output /dev/null


  docker inspect --format='{{json .State.Health}}' ai-traefik | jq

 docker inspect --format='{{.Name}} {{.State.Health.Status}}' $(docker ps -q)

 ## Check health status of all running containers
docker inspect --format='{{.Name}}{{"\t"}}{{if .State.Health}}{{.State.Health.Status}}{{else}}no healthcheck{{end}}' $(docker ps -q) | column -t
