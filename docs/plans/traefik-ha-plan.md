# Traefik HA Plan

## Architecture

- **VIP:** 192.168.1.51 (keepalived VRRP, floats between nodes)
- **Master:** 192.168.1.62 — Traefik always running, owns certificatesResolvers (ACME/Cloudflare DNS-01)
- **Backup:** 192.168.1.63 — Traefik always running, mounts shared acme.json via NFS, no certificatesResolvers
- **Shared cert storage:** NFS export from 192.168.1.63 → mounted on 192.168.1.62 at `/mnt/ai-files/traefik/acme/`
- keepalived manages VIP only — no container start/stop

**Limitation:** If master is down >60 days, certs expire. Acceptable for homelab.

---

## Rollout sequence

### Step 1 — Build LXCs
- Create two LXCs on separate Proxmox hosts
- Install Docker + Docker Compose on each
- Confirm ports 80/443 free: `ss -tlnp | grep -E ':80|:443'`
- Confirm interface name: `ip link show`

### Step 2 — NFS shared cert storage

On 192.168.1.63:
```bash
apt-get install -y nfs-kernel-server
```
Add to `/etc/exports`:
```
/mnt/ai-files/traefik/acme  192.168.1.62(rw,sync,no_subtree_check,no_root_squash)
```
```bash
exportfs -ra
systemctl enable --now nfs-server
```

On 192.168.1.62:
```bash
apt-get install -y nfs-common
mkdir -p /mnt/ai-files/traefik/acme
```
Add to `/etc/fstab`:
```
192.168.1.63:/mnt/ai-files/traefik/acme  /mnt/ai-files/traefik/acme  nfs  defaults,_netdev  0  0
```
```bash
mount -a
ls -la /mnt/ai-files/traefik/acme/acme.json   # must be 600
```

### Step 3 — Deploy Traefik on both nodes

Run Context7 (`/context7`) to verify current Traefik image tag before writing compose.

Key differences between nodes:

| Setting | Master (.62) | Backup (.63) |
|---|---|---|
| `restart` | `unless-stopped` | `unless-stopped` |
| `certificatesResolvers` | Yes (Cloudflare DNS-01) | No |
| `acme.json` path | `/mnt/ai-files/traefik/acme/acme.json` (NFS mount) | `/mnt/ai-files/traefik/acme/acme.json` (local) |

Both nodes: add `--ping=true` and `--api.insecure=true` to Traefik command args (needed for keepalived health check).

### Step 4 — keepalived

Install on both:
```bash
apt-get install -y keepalived
```

Health check script (both nodes) — `/etc/keepalived/check_traefik.sh`:
```bash
#!/bin/bash
curl -sf http://localhost:8080/ping > /dev/null 2>&1
```
```bash
chmod +x /etc/keepalived/check_traefik.sh
```

Master config `/etc/keepalived/keepalived.conf`:
```
vrrp_script chk_traefik {
    script "/etc/keepalived/check_traefik.sh"
    interval 5
    weight -20
    fall 2
    rise 2
}

vrrp_instance TRAEFIK_HA {
    state MASTER
    interface <INTERFACE>
    virtual_router_id 51
    priority 150
    advert_int 1
    unicast_src_ip 192.168.1.62
    unicast_peer {
        192.168.1.63
    }
    authentication {
        auth_type PASS
        auth_pass <SHARED_SECRET>
    }
    virtual_ipaddress {
        192.168.1.51/24
    }
    track_script {
        chk_traefik
    }
}
```

Backup config — same but `state BACKUP`, `priority 100`, swap `unicast_src_ip` / `unicast_peer`.

Start both:
```bash
systemctl enable --now keepalived
```

### Step 5 — Internal DNS

UniFi: add static hostname → `192.168.1.51` for each service.

### Step 6 — Configure DNS-01 certs (master only)

Set `CF_DNS_API_TOKEN` in `.env` on master. Verify in Traefik logs after start:
```bash
docker logs traefik --tail 50 | grep -i acme
```

### Step 7 — Internal testing

- Hit each service hostname from a device on the LAN
- Verify HTTPS and any middleware (auth, redirects)
- Check Traefik dashboard on master: `http://192.168.1.62:8080`

### Step 8 — Failover test

```bash
# On master — stop keepalived
systemctl stop keepalived

# On backup — verify VIP moved
ip addr show | grep 192.168.1.51
# Verify traffic still works from client
```

### Step 9 — Recovery test

```bash
systemctl start keepalived   # on master
# VIP returns to master, backup loses VIP
```

### Step 10 — Full LXC shutdown test

Shut down the master LXC entirely from Proxmox. Confirm backup picks up VIP and serves traffic. Bring master back, confirm recovery.

### Step 11 — Expose externally

Only after steps 7-10 pass:
- Forward TCP 443 from UCG-Max to `192.168.1.51`
- Review all Traefik routers — expose only explicitly approved ones

---

## Placeholders

| Placeholder | Where |
|---|---|
| `<INTERFACE>` | Network interface name on each node |
| `<SHARED_SECRET>` | Same random string on both keepalived configs — `openssl rand -hex 16` |
| `CF_DNS_API_TOKEN` | Cloudflare API token in `.env` on master |
| Service hostnames | UniFi DNS entries pointing at 192.168.1.51 |