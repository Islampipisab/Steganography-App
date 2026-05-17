# Deploy/update stego_project to Ubuntu cloud server and configure SSL.
# Usage:
#   .\deploy.ps1
#   .\deploy.ps1 -BootstrapSsl
#   .\deploy.ps1 -User root -Server 46.101.244.129 -Domain stegax.design -BootstrapSsl

param(
    [string]$User = "root",
    [string]$Server = "46.101.244.129",
    [string]$Domain = "stegax.design",
    [string]$RemotePath = "/root",
    [switch]$BootstrapSsl
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectName = "stego_project"

if ((Split-Path -Leaf $ScriptDir) -eq $ProjectName) {
    $SourceDir = $ScriptDir
} else {
    $SourceDir = Join-Path $ScriptDir $ProjectName
}

if (-not (Test-Path $SourceDir)) {
    throw "Project folder not found: $SourceDir"
}

$Dest = "${User}@${Server}:${RemotePath}"
Write-Host "Uploading $SourceDir to $Dest ..."
scp -r $SourceDir $Dest

$BootstrapSslFlag = if ($BootstrapSsl.IsPresent) { "1" } else { "0" }
$RemoteScript = @"
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

DOMAIN="$Domain"
WWW_DOMAIN="www.$Domain"
BOOTSTRAP_SSL="$BootstrapSslFlag"
APP_DIR="/root/stego_project"

apt-get update
apt-get install -y python3-venv python3-pip nginx certbot python3-certbot-nginx

cd "`$APP_DIR"
python3 -m venv venv
. venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

cp deploy/stego-web.service /etc/systemd/system/stego-web.service
systemctl daemon-reload
systemctl enable stego-web
systemctl restart stego-web

if [ "`$BOOTSTRAP_SSL" = "1" ]; then
  cat > /etc/nginx/sites-available/`$DOMAIN <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name `$DOMAIN `$WWW_DOMAIN;

    location / {
        include proxy_params;
        proxy_pass http://127.0.0.1:5000;
        proxy_connect_timeout 600s;
        proxy_send_timeout 600s;
        proxy_read_timeout 600s;
        send_timeout 600s;
        client_body_timeout 600s;
        client_max_body_size 200M;
    }
}
EOF

  ln -sf /etc/nginx/sites-available/`$DOMAIN /etc/nginx/sites-enabled/`$DOMAIN
  rm -f /etc/nginx/sites-enabled/default
  nginx -t
  systemctl restart nginx

  certbot --nginx \
    -d "`$DOMAIN" \
    -d "`$WWW_DOMAIN" \
    --non-interactive \
    --agree-tos \
    --register-unsafely-without-email \
    --redirect
else
  nginx -t
  systemctl reload nginx
fi

echo "stego-web: `$(systemctl is-active stego-web)"
echo "nginx: `$(systemctl is-active nginx)"
"@

$EscapedRemoteScript = $RemoteScript -replace "'", '''"''"'''
Write-Host "Running remote update steps on ${User}@${Server} ..."
ssh "${User}@${Server}" "bash -lc '$EscapedRemoteScript'"

Write-Host ""
Write-Host "Deployment complete."
Write-Host "App URL: https://$Domain"
if (-not $BootstrapSsl.IsPresent) {
    Write-Host "Tip: for first-time SSL + Nginx setup, run once with -BootstrapSsl."
}
