#!/bin/sh
# certbot deploy hook: copies the renewed certificate where the service user
# can read it, then restarts the service (the server reads the certificate
# only at start). certbot sets RENEWED_LINEAGE; the fallback is for running
# this by hand right after the first issuance.
#   sudo cp deploy/install-cert.sh /usr/local/bin/social-lab-install-cert
#   sudo chmod 755 /usr/local/bin/social-lab-install-cert
set -eu
LIVE="${RENEWED_LINEAGE:-$(ls -d /etc/letsencrypt/live/*/ | head -n 1)}"
DEST=/opt/social-lab/certs
install -d -o root -g sociallab -m 750 "$DEST"
install -o root -g sociallab -m 640 "$LIVE/fullchain.pem" "$DEST/fullchain.pem"
install -o root -g sociallab -m 640 "$LIVE/privkey.pem" "$DEST/privkey.pem"
systemctl restart social-lab 2>/dev/null || true
echo "certificate installed from $LIVE"
