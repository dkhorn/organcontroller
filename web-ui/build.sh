#!/bin/bash
# Build and deploy the organ controller web UI

set -e

echo "Building React app..."
cd /home/daniel/organcontroller/web-ui
npm run build

echo "Build complete! Static files are in web-ui/build/"
echo ""
echo "To serve with nginx:"
echo "1. Install nginx: sudo apt install nginx"
echo "2. Copy nginx config: sudo cp /home/daniel/organcontroller/web-ui/nginx.conf /etc/nginx/sites-available/organcontroller"
echo "3. Enable site: sudo ln -s /etc/nginx/sites-available/organcontroller /etc/nginx/sites-enabled/"
echo "4. Remove default site: sudo rm /etc/nginx/sites-enabled/default"
echo "5. Restart nginx: sudo systemctl restart nginx"
