# Dashboard Deployment - Recent Updates

## Changes Made

### 1. Fixed Docker Path Issues
- Updated Dockerfiles to correctly copy files from build context
- Fixed app.py to work in both Docker and local environments using `DOCKER_ENV` variable

### 2. Added Full Project Dependencies
- Dashboard now installs both Flask dependencies AND main project dependencies
- This allows the "Run Analysis" feature to work inside Docker
- Includes: `influxdb-client`, `python-dotenv`, `pandas`, `numpy`, etc.

### 3. Volume Mounts
The following are now mounted in the container:
- **`../data:/app/data`** - Data directory (writable for analysis output)
- **`../live:/app/live:ro`** - Live scripts (read-only)
- **`../.env:/app/.env:ro`** - Environment file with InfluxDB credentials (read-only)

### 4. Environment Variables
- `DOCKER_ENV=1` - Tells app.py to use `/app` as base directory
- `FLASK_ENV=production` - Flask environment
- `FLASK_DEBUG=0` - Disable debug mode

## How to Deploy on Server

### Step 1: Stop Current Container
```bash
cd ~/order-book-test/order-book/dashboard
docker-compose down
```

### Step 2: Pull Latest Code
```bash
cd ~/order-book-test/order-book
git pull
```

### Step 3: Rebuild and Start
```bash
cd dashboard
docker-compose up -d --build
```

This will:
1. Rebuild the image with all dependencies
2. Mount all required directories and files
3. Start the dashboard on port 5000

### Step 4: Verify It's Working
```bash
# Check container status
docker ps | grep orderbook-dashboard

# Check logs
docker logs -f orderbook-dashboard

# Test API
curl http://localhost:5000/api/stats
```

### Step 5: Test Run Analysis Feature
1. Open dashboard: http://your-server-ip:5000
2. Click "Run New Analysis" button
3. Fill in the form (symbol, interval, etc.)
4. Click "Run Analysis"
5. Wait for it to complete
6. New file should appear in the file list

## Troubleshooting

### Issue: Container keeps restarting
```bash
docker logs orderbook-dashboard
```
Look for Python errors or missing dependencies.

### Issue: "Analyzer script not found"
Check if `/app/live` is mounted correctly:
```bash
docker exec orderbook-dashboard ls -la /app/live
```
Should show `price_change_analyzer.py`

### Issue: "Permission denied" when running analysis
The data directory needs write permissions:
```bash
chmod -R 775 ~/order-book-test/order-book/data
```

### Issue: Analysis fails with InfluxDB error
1. Check if `.env` file exists and is mounted:
```bash
docker exec orderbook-dashboard cat /app/.env
```

2. Verify InfluxDB connection from container:
```bash
docker exec orderbook-dashboard python -c "from dotenv import load_dotenv; import os; load_dotenv(); print(os.getenv('INFLUXDB_URL'))"
```

3. Make sure InfluxDB container is running:
```bash
docker ps | grep influxdb
```

### Issue: Running analysis but no output file
1. Check container logs during analysis:
```bash
docker logs -f orderbook-dashboard
```

2. Verify data directory is writable:
```bash
docker exec orderbook-dashboard ls -la /app/data
```

3. Check if analysis completed successfully (look for error output)

## File Structure in Container

```
/app/
├── app.py                    # Dashboard Flask app
├── templates/
│   └── index.html
├── static/
│   ├── css/
│   └── js/
├── data/                     # Mounted from ../data
│   └── price_changes_*.json
├── live/                     # Mounted from ../live
│   └── price_change_analyzer.py
└── .env                      # Mounted from ../.env
```

## Network Configuration

The dashboard needs to connect to InfluxDB. Make sure:
1. InfluxDB container is running
2. InfluxDB is accessible from dashboard container
3. `.env` file has correct InfluxDB URL

If both containers are on the same Docker network:
```bash
# Check network
docker network ls
docker network inspect <network-name>
```

## Production Recommendations

1. **Use production compose file**:
   ```bash
   docker-compose -f docker-compose.production.yml up -d --build
   ```

2. **Set up reverse proxy** (nginx) for HTTPS

3. **Monitor logs**:
   ```bash
   docker logs -f orderbook-dashboard
   ```

4. **Set up automatic restarts** (already configured with `restart: unless-stopped`)

5. **Backup data directory** regularly:
   ```bash
   tar -czf data-backup-$(date +%Y%m%d).tar.gz data/
   ```
