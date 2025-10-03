# Dashboard Docker Deployment

## Quick Start

### Option 1: Using Docker Compose (Recommended)

```bash
# From the dashboard directory
cd dashboard
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

### Option 2: Using Docker directly

```bash
# Build image
docker build -t orderbook-dashboard -f dashboard/Dockerfile .

# Run container
docker run -d \
  --name orderbook-dashboard \
  -p 5000:5000 \
  -v $(pwd)/data:/app/data:ro \
  -v $(pwd)/live:/app/live:ro \
  orderbook-dashboard

# View logs
docker logs -f orderbook-dashboard

# Stop
docker stop orderbook-dashboard
docker rm orderbook-dashboard
```

## Server Deployment

### Prerequisites

1. **Install Docker & Docker Compose** on your server:
```bash
# Ubuntu/Debian
sudo apt update
sudo apt install docker.io docker-compose

# Start Docker service
sudo systemctl start docker
sudo systemctl enable docker

# Add user to docker group (optional, to run without sudo)
sudo usermod -aG docker $USER
# Log out and back in for this to take effect
```

2. **Clone repository** on server:
```bash
git clone <your-repo-url>
cd order-book
```

### Deploy Dashboard

```bash
# Navigate to dashboard directory
cd dashboard

# Build and start the dashboard
docker-compose up -d

# Verify it's running
docker-compose ps
curl http://localhost:5000/api/stats
```

### Access Dashboard

The dashboard will be available at:
- **Local**: http://localhost:5000
- **Remote**: http://your-server-ip:5000

For production, consider:
- Setting up a reverse proxy (nginx/caddy)
- Enabling HTTPS with SSL certificates
- Configuring firewall rules

## Configuration

### Port Configuration

To change the port, edit `docker-compose.yml`:

```yaml
ports:
  - "8080:5000"  # Map to port 8080 instead
```

### Volume Mounts

The following directories are mounted:

- **`../data:/app/data:ro`** - Read-only access to data files
- **`../live:/app/live:ro`** - Read-only access to analyzer scripts (for run-analysis API)

To mount different paths, edit `docker-compose.yml`:

```yaml
volumes:
  - /path/to/your/data:/app/data:ro
  - /path/to/your/live:/app/live:ro
```

### Environment Variables

Available environment variables:

```yaml
environment:
  - FLASK_ENV=production          # production or development
  - FLASK_DEBUG=0                 # 0 or 1
  - PORT=5000                     # Port to run on (if modified in app.py)
```

## Reverse Proxy Setup (Production)

### Nginx Configuration

Create `/etc/nginx/sites-available/orderbook-dashboard`:

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable and restart nginx:

```bash
sudo ln -s /etc/nginx/sites-available/orderbook-dashboard /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### SSL with Certbot

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

## Monitoring & Maintenance

### View Logs

```bash
# Real-time logs
docker-compose logs -f

# Last 100 lines
docker-compose logs --tail=100

# Specific service
docker-compose logs dashboard
```

### Check Health Status

```bash
# Container health
docker-compose ps

# Application health
curl http://localhost:5000/api/stats
```

### Restart Dashboard

```bash
# Graceful restart
docker-compose restart

# Rebuild and restart (after code changes)
docker-compose up -d --build
```

### Update Deployment

```bash
# Pull latest code
git pull

# Rebuild and restart
cd dashboard
docker-compose down
docker-compose up -d --build
```

## Troubleshooting

### Container won't start

```bash
# Check logs
docker-compose logs

# Check if port is already in use
sudo lsof -i :5000

# Remove and recreate
docker-compose down
docker-compose up -d
```

### No data files showing

```bash
# Check if data directory exists and has files
ls -la ../data/price_changes_*.json

# Check volume mount
docker-compose exec dashboard ls -la /app/data

# Verify permissions
ls -la ../data
```

### Connection refused from external IP

```bash
# Check if container is running
docker-compose ps

# Check firewall
sudo ufw status
sudo ufw allow 5000/tcp

# Check if Docker is listening on all interfaces
docker-compose exec dashboard netstat -tuln | grep 5000
```

### High memory usage

```bash
# Check resource usage
docker stats orderbook-dashboard

# Limit resources in docker-compose.yml:
services:
  dashboard:
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: '0.5'
```

## Security Considerations

1. **Read-only volumes**: Data and scripts are mounted read-only (`:ro`)
2. **No host network**: Container runs in isolated network
3. **Non-root user**: Consider adding a non-root user in Dockerfile
4. **CORS**: Disable or restrict CORS in production
5. **Rate limiting**: Add rate limiting with nginx or application middleware

### Recommended Production Settings

Edit `app.py` for production:

```python
# Disable debug mode
app.run(debug=False, host='0.0.0.0', port=5000)

# Restrict CORS
CORS(app, origins=["https://your-domain.com"])
```

## Performance Optimization

### Use Production WSGI Server

Update `Dockerfile` to use gunicorn:

```dockerfile
# Add to requirements.txt
# gunicorn==21.2.0

# Update CMD
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "dashboard.app:app"]
```

### Enable Caching

Add nginx caching for static files:

```nginx
location /static/ {
    proxy_pass http://localhost:5000;
    proxy_cache_valid 200 1d;
    expires 1d;
}
```

## Backup & Recovery

### Backup Data

```bash
# Backup data directory
tar -czf orderbook-data-$(date +%Y%m%d).tar.gz ../data/

# Automated daily backup (crontab)
0 2 * * * cd /path/to/order-book && tar -czf backup/data-$(date +\%Y\%m\%d).tar.gz data/
```

### Restore Data

```bash
# Extract backup
tar -xzf orderbook-data-20251003.tar.gz

# Restart dashboard
docker-compose restart
```

## Multi-Instance Deployment

To run multiple instances behind a load balancer:

```yaml
services:
  dashboard:
    deploy:
      replicas: 3
```

Then use nginx for load balancing:

```nginx
upstream dashboard_backend {
    least_conn;
    server localhost:5001;
    server localhost:5002;
    server localhost:5003;
}
```
