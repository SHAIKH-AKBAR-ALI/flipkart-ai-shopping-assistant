#!/bin/bash
set -e

echo "Starting deployment setup for Flipkart AI Shopping Assistant..."

# 1. Update system and install dependencies
sudo apt-get update
sudo apt-get install -y python3.11 python3.11-venv python3-pip nginx ufw git

# 2. Set up project directory
PROJECT_DIR="/var/www/flipkart-rag"
sudo mkdir -p $PROJECT_DIR
sudo chown -R ubuntu:ubuntu $PROJECT_DIR

# Copy application files (assumes this script is run from the project root)
# Alternatively, you can clone here using: git clone <repo_url> $PROJECT_DIR
cp -r backend $PROJECT_DIR/

# 3. Create virtual environment and install dependencies
cd $PROJECT_DIR/backend
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 4. Create .env file with placeholder API keys
cat <<EOF > .env
PORT=8080
OPENAI_API_KEY="your_openai_api_key_here"
GROQ_API_KEY="your_groq_api_key_here"
ASTRA_DB_API_ENDPOINT="your_astra_endpoint_here"
ASTRA_DB_APPLICATION_TOKEN="your_astra_token_here"
ASTRA_DB_KEYSPACE="your_astra_keyspace_here"
EOF
echo ".env file created with placeholders. Please update them later."

# 5. Set up Systemd Service
sudo cp /home/ubuntu/flipkart.service /etc/systemd/system/flipkart.service
sudo systemctl daemon-reload
sudo systemctl enable flipkart.service
sudo systemctl start flipkart.service

# 6. Configure Nginx
sudo cp /home/ubuntu/flipkart.nginx.conf /etc/nginx/sites-available/flipkart
sudo ln -sf /etc/nginx/sites-available/flipkart /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx

# 7. Configure Firewall
sudo ufw allow ssh
sudo ufw allow 80/tcp
sudo ufw allow 8080/tcp
sudo ufw --force enable

echo "======================================================"
echo "Deployment Complete!"
echo "Your app should be starting on port 8080 and exposed via Nginx on port 80."
echo "Please update the .env file at $PROJECT_DIR/backend/.env with real API keys and restart the service:"
echo "  sudo systemctl restart flipkart.service"
echo "======================================================"
