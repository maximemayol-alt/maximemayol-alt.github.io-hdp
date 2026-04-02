#!/bin/bash
# Déploiement rapide sur un VPS Ubuntu
# Usage : ssh root@ton-vps 'bash -s' < deploy.sh

set -e

echo "=== Installation des dépendances ==="
apt-get update -qq
apt-get install -y -qq python3 python3-pip git

echo "=== Clonage du repo ==="
cd /opt
rm -rf betting-bot
git clone -b claude/telegram-basketball-betting-bot-QtqH6 \
  https://github.com/maximemayol-alt/maximemayol-alt.github.io-hdp.git betting-bot
cd betting-bot/bot

echo "=== Installation Python ==="
pip3 install -r requirements.txt

echo "=== Création du .env ==="
if [ ! -f .env ]; then
  cat > .env << 'EOF'
TELEGRAM_BOT_TOKEN=8288459689:AAGtTW21nslunUDXAQMJtN53B5TV23nhUVM
TELEGRAM_CHAT_ID=499940076
ODDS_API_KEY=c0b9eb645279c8777e7f5f4f13f00f98
EOF
fi

echo "=== Installation du service systemd ==="
cat > /etc/systemd/system/betting-bot.service << 'EOF'
[Unit]
Description=Basketball O/U Betting Bot
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/betting-bot/bot
ExecStart=/usr/bin/python3 main.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable betting-bot
systemctl restart betting-bot

echo "=== Bot démarré ! ==="
echo "Commandes utiles :"
echo "  systemctl status betting-bot    # Statut"
echo "  journalctl -u betting-bot -f    # Logs en direct"
echo "  systemctl restart betting-bot   # Redémarrer"
echo "  systemctl stop betting-bot      # Arrêter"
