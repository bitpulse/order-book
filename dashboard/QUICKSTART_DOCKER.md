# Dashboard Docker Quick Start

## 🚀 Super Quick Start

```bash
cd dashboard
./deploy.sh dev up
```

Dashboard available at: http://localhost:5000

## 📋 Prerequisites

- Docker installed
- Docker Compose installed
- Data files in `../data/` directory

## 🎯 Common Commands

### Development Mode

```bash
# Start
./deploy.sh dev up

# Stop
./deploy.sh dev down

# View logs
./deploy.sh dev logs

# Check status
./deploy.sh dev status

# Restart
./deploy.sh dev restart
```

### Production Mode

```bash
# Start
./deploy.sh prod up

# Rebuild and start
./deploy.sh prod rebuild

# Stop
./deploy.sh prod down

# View logs
./deploy.sh prod logs

# Check status
./deploy.sh prod status
```

## 🔧 Manual Docker Commands

If you prefer not to use the deploy script:

### Development

```bash
# Start
docker-compose up -d

# Stop
docker-compose down

# View logs
docker-compose logs -f
```

### Production

```bash
# Start
docker-compose -f docker-compose.production.yml up -d

# Stop
docker-compose -f docker-compose.production.yml down

# View logs
docker-compose -f docker-compose.production.yml logs -f
```

## 🌐 Accessing the Dashboard

### Local Access
- Development: http://localhost:5000
- Production: http://localhost:5000

### Remote Access (Server)
- http://YOUR_SERVER_IP:5000

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
./deploy.sh prod rebuild
```

## 📝 Configuration

### Change Port

Edit `docker-compose.yml` or `docker-compose.production.yml`:

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

- Full deployment guide: [DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md)
- Dashboard features: [README.md](README.md)
- Project overview: [../CLAUDE.md](../CLAUDE.md)
