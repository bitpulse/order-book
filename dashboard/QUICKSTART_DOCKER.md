# Dashboard Docker Quick Start

## 🚀 Super Quick Start

```bash
cd dashboard
./deploy.sh up
```

Dashboard available at: http://localhost:5000

## 📋 Prerequisites

- Docker installed
- Docker Compose installed
- Data files in `../data/` directory

## 🎯 Common Commands

```bash
# Start
./deploy.sh up

# Stop
./deploy.sh down

# View logs
./deploy.sh logs

# Check status
./deploy.sh status

# Restart
./deploy.sh restart

# Rebuild and start
./deploy.sh rebuild
```

## 🔧 Manual Docker Commands

If you prefer not to use the deploy script:

```bash
# Start
docker-compose up -d

# Stop
docker-compose down

# View logs
docker-compose logs -f

# Rebuild and start
docker-compose up -d --build
```

## 🌐 Accessing the Dashboard

### Local Access

- <http://localhost:5000>

### Remote Access (Server)

- <http://YOUR_SERVER_IP:5000>

⚠️ **Note**: Make sure port 5000 is open in your firewall:

```bash
sudo ufw allow 5000/tcp
```

## 📊 Verify Installation

```bash
# Check if container is running
docker ps | grep orderbook-dashboard

# Test API endpoint
curl http://localhost:5000/api/stats

# Check logs
docker logs orderbook-dashboard
```

## 🐛 Troubleshooting

### Container won't start

```bash
docker-compose logs
```

### Port already in use

```bash
# Find what's using port 5000
sudo lsof -i :5000

# Kill the process or change port in docker-compose.yml
```

### No data showing

```bash
# Check if data files exist
ls -la ../data/price_changes_*.json

# Verify volume mount
docker exec orderbook-dashboard ls -la /app/data
```

### Permission issues

```bash
# Fix data directory permissions
chmod -R 755 ../data
```

## 🔄 Updating

```bash
# Pull latest code
git pull

# Rebuild and restart
./deploy.sh rebuild
```

## 📝 Configuration

### Change Port

Edit `docker-compose.yml`:

```yaml
ports:
  - "8080:5000"  # Change 8080 to your preferred port
```

### Change Data Directory

Edit volume mount in compose file:

```yaml
volumes:
  - /custom/path/to/data:/app/data:ro
```

## 🛑 Completely Remove

```bash
# Stop and remove container
docker-compose down

# Remove image
docker rmi orderbook-dashboard

# Remove volumes (if any)
docker volume prune
```

## 📖 More Information

- Dashboard features: [README.md](README.md)
- Project overview: [../CLAUDE.md](../CLAUDE.md)
