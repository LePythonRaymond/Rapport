# Stop containers
docker compose down

# Add what you want
nano /root/Dockerfile
nano /root/docker-compose.yml

# Rebuild with latest n8n version
docker compose build --no-cache

# Start again
docker compose up -d