PROJECT_DIR="$(pwd)"  # Auto-detects current directory
SERVICE_FILE="/etc/systemd/system/tcpsearchserver.service"
PYTHON_PATH="$(which python3)"

# Validate paths
if [ ! -f "$PROJECT_DIR/server.py" ]; then
  echo "Error: server.py not found in $PROJECT_DIR"
  exit 1
fi

if [ -z "$PYTHON_PATH" ]; then
  echo "Error: python3 not found in PATH"
  exit 1
fi

# Create service file with proper escaping
sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=TCP Search Server
After=network.target
StartLimitIntervalSec=60
StartLimitBurst=3

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$PROJECT_DIR
ExecStart=$PYTHON_PATH $PROJECT_DIR/server.py
Restart=on-failure
RestartSec=5s
KillSignal=SIGTERM
TimeoutStopSec=30
Environment="PYTHONPATH=$PROJECT_DIR"
StandardOutput=journal
StandardError=journal
SyslogIdentifier=tcpsearchserver

# Security hardening
ProtectSystem=full
PrivateTmp=true
NoNewPrivileges=true
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
EOF

# Systemd commands
echo "Reloading systemd..."
sudo systemctl daemon-reload

echo "Enabling service..."
sudo systemctl enable tcpsearchserver

echo "Starting service..."
sudo systemctl start tcpsearchserver

# Verification
sleep 2  # Allow time for service start
SERVICE_STATUS=$(systemctl is-active tcpsearchserver)

if [ "$SERVICE_STATUS" = "active" ]; then
  echo -e "\n\033[32mService started successfully!\033[0m"
  echo "Check status: systemctl status tcpsearchserver"
  echo "View logs: journalctl -u tcpsearchserver -f"
else
  echo -e "\n\033[31mService failed to start!\033[0m"
  journalctl -u tcpsearchserver --no-pager -n 20
  exit 1
fi