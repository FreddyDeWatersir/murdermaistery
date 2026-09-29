#!/usr/bin/env bash
# One-time setup for the murder mystery on the shop's Hetzner box (D-176).
#
#   sudo bash /srv/mystery/repo/deploy/setup-server.sh
#
# Run it after steps 1 to 4 of deploy/README.md (the user, the deploy key, the
# clone, uv). Safe to run again: every step either checks first or only puts
# the repo's copy of a file in place.
#
# What it deliberately does NOT do: touch the shop's Caddyfile, reload Caddy, or
# start the game. Each of those needs something only you can supply first (a
# password, an API key, a case), and a script that reloads the web server in
# front of a live shop should not be guessing.

set -euo pipefail

APP=/srv/mystery
REPO=$APP/repo
DEPLOY=$REPO/deploy

step() { echo "== $*"; }
die() {
	echo "  $*" >&2
	exit 1
}

[[ $EUID -eq 0 ]] || die "Run it with sudo."
id mystery >/dev/null 2>&1 || die "There is no 'mystery' user yet. README step 2."
[[ -d $REPO/.git ]] || die "Nothing is cloned at $REPO. README step 4."
command -v uv >/dev/null || die "uv is not installed. README step 5."
command -v caddy >/dev/null || die "No caddy on this machine, which here means something else is wrong."

step "folders"
# 750: the game can read and write them, you get in with sudo, nobody else.
install -d -o mystery -g mystery -m 750 "$APP/shared" "$APP/var" "$APP/var/inbox"
if [[ ! -f $APP/shared/.env ]]; then
	install -o mystery -g mystery -m 600 /dev/null "$APP/shared/.env"
	echo "  made an empty $APP/shared/.env for the API key (README step 7)"
fi

step "python packages"
# --locked: install exactly what uv.lock says, and refuse if the lock is stale,
# so the server never quietly runs versions nobody tested.
sudo -u mystery -H bash -c "cd $REPO && uv sync --locked --no-dev"

step "service"
install -m 644 "$DEPLOY/mystery.service" /etc/systemd/system/mystery.service
systemctl daemon-reload
systemctl enable mystery >/dev/null 2>&1
echo "  installed and enabled (it starts with the machine, once there is a case)"

step "mysteryctl"
install -m 755 "$DEPLOY/mysteryctl" /usr/local/bin/mysteryctl
echo "  try: sudo mysteryctl help"

step "caddy site block"
install -d -m 755 /etc/caddy/sites
install -m 644 "$DEPLOY/mystery.caddy" /etc/caddy/sites/mystery.caddy
echo "  in place at /etc/caddy/sites/mystery.caddy, not served until README step 9"

echo
echo "Done. Next: README step 7 (API key)."
