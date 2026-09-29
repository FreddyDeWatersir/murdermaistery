# Running the mystery on the Hetzner box

The game runs beside the 7Seas shop on the same server, as its own user, on its
own port, behind its own password, at `https://mystery.7seastcg.com` (D-176,
D-177). The shop does not know it is there, apart from one import line in its
Caddyfile.

```
browser ── DNS (Porkbun): mystery.7seastcg.com → 157.180.80.106
   ▼
Caddy on :443 ── 7seastcg.com          → 127.0.0.1:3000  shop  (user 7seas)
              └─ mystery.7seastcg.com  → password → 127.0.0.1:8000  game  (user mystery)
```

```
/srv/mystery/
  repo/          this repository (git clone, read-only deploy key)
  shared/.env    ANTHROPIC_API_KEY, readable only by the game
  shared/run.env which case is served (written by `mysteryctl play`)
  var/           cases, art, session transcripts
/etc/systemd/system/mystery.service   from deploy/mystery.service
/etc/caddy/sites/mystery.caddy        from deploy/mystery.caddy
/etc/caddy/mystery-users              tester password hash, never in git
/usr/local/bin/mysteryctl             from deploy/mysteryctl
```

Cases are made on your PC and only served here (D-176). The server never
drafts, so it never needs the image key and can never spend money on a case.

---

## First-time setup

Run these one at a time and read what each prints. Everything from step 2 on
happens over SSH as `federico`.

### 0. On your PC: commit and push `deploy/`

The server installs from the clone, so these files have to be on GitHub first.

### 1. DNS (Porkbun, in the browser)

Add a record to 7seastcg.com: type **A**, host **mystery**, answer
**157.180.80.106**. If the shop's own record has an **AAAA** (IPv6) twin, add
one for `mystery` too, pointing at the same IPv6 address. Do this first:
it can take a few minutes to spread, and Caddy needs it to get the certificate.

### 2. The game's user

```bash
sudo adduser --system --group --home /srv/mystery --shell /usr/sbin/nologin mystery
```

A user for the program, not for a person: no password, cannot log in.

### 3. A deploy key, so the server can read the repo and nothing else

```bash
sudo -u mystery mkdir -p -m 700 /srv/mystery/.ssh
sudo -u mystery ssh-keygen -t ed25519 -N "" -C "mystery@hetzner" -f /srv/mystery/.ssh/id_ed25519
sudo cat /srv/mystery/.ssh/id_ed25519.pub
```

Copy the line it prints (the public half, safe to share). On GitHub:
**murdermaistery → Settings → Deploy keys → Add deploy key**, title
`hetzner`, paste, and leave **Allow write access unticked**. If this server is
ever compromised, the most the key can do is read this one repo.

### 4. Clone

```bash
sudo -u mystery -H git clone git@github.com:FreddyDeWatersir/murdermaistery.git /srv/mystery/repo
```

The first time, it asks whether to trust github.com and shows a fingerprint.
Compare it with the ED25519 line on GitHub's page "GitHub's SSH key
fingerprints", then type `yes`.

### 5. uv (installs Python packages)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sudo env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh
uv --version
```

### 6. The setup script

```bash
sudo bash /srv/mystery/repo/deploy/setup-server.sh
```

Folders, packages, the service, `mysteryctl`, and the Caddy site file. It does
not start anything or reload Caddy.

### 7. The API key

Make a **separate** key for the server in the Anthropic Console, named
`hetzner-mystery`, ideally in a workspace with a monthly spend limit. Then:

```bash
sudo nano /srv/mystery/shared/.env
```

One line, `ANTHROPIC_API_KEY=` followed by the key. Ctrl+O, Enter, Ctrl+X. A
separate key means you can revoke the server's without touching your PC's, and
the Console shows exactly what the tests cost.

### 8. A case

On your PC, in the repo:

```powershell
uv run python -m mystery.cli --bundle CASE_ID
scp CASE_ID.zip federico@157.180.80.106:
```

On the server:

```bash
sudo mysteryctl add ~/CASE_ID.zip
sudo mysteryctl play CASE_ID
```

`play` waits until the game answers on port 8000 and says so. Nothing outside
can reach it yet.

### 9. Open the door

First the password (generate it in Bitwarden and save it there first):

```bash
sudo mysteryctl password
```

Then the one line in the **shop's** repo. At the end of `deploy/Caddyfile`:

```
# Other apps on this box bring their own site blocks (the murder mystery's is
# /etc/caddy/sites/mystery.caddy). Keeping them out of this file means a shop
# deploy can never delete them.
import /etc/caddy/sites/*.caddy
```

Commit and push it in the shop repo, bring the server's shop clone up to date
the way the shop's own `deploy/README.md` says, then install it, checking
before anything goes live:

```bash
sudo caddy validate --config /srv/7seas/repo/deploy/Caddyfile --adapter caddyfile
sudo cp /etc/caddy/Caddyfile /etc/caddy/Caddyfile.bak
sudo cp /srv/7seas/repo/deploy/Caddyfile /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

If `validate` complains, stop there: nothing has changed yet and the shop is
fine.

### 10. Check both

- `https://mystery.7seastcg.com` asks for a login; `tester` and the password
  get you in.
- `https://7seastcg.com` still loads, and `/admin` still asks for its own login.

---

## Per test group

```bash
sudo mysteryctl password        # a new password for this group
sudo mysteryctl fresh           # a clean game (or: play OTHER_CASE_ID)
```

Send them the link and the password. Afterwards:

```bash
sudo mysteryctl transcripts
```

and on your PC: `scp -r federico@157.180.80.106:transcripts .`

**Until rooms exist (D-178) the server holds one game at a time.** Everybody who
logs in shares it, and any restart (`fresh`, `play`, `update`, a reboot, a
crash) starts a new one. So: one group per evening, and no `update` while
somebody is playing.

## Updating the code

Push from your PC, then on the server:

```bash
sudo mysteryctl update
```

Pulls, reinstalls packages from `uv.lock`, refreshes the service and the Caddy
site file (validating before any reload), restarts, and replaces itself last.

## When something is wrong

```bash
sudo mysteryctl status          # running? which case?
sudo mysteryctl logs            # the last 50 lines, then live
free -h                         # memory; the game is capped at 1 GB
```

If Caddy ever refuses to start, the shop is down too. The fix is always the same:
`sudo cp /etc/caddy/Caddyfile.bak /etc/caddy/Caddyfile && sudo systemctl reload caddy`,
then read what `caddy validate` says about the new one.
