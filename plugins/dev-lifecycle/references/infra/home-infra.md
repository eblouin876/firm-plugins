<!--
library: home-infra
versions-covered: "n/a"
last-verified: 2026-07-09
provenance: manual
sources: []
-->

# Home infrastructure (Goatenheim)

Running a home box (Goatenheim) as a beta/staging server and self-hosting host that stays reachable and recovers on its own — including while you're on the road. Read after choosing the home-infra target. The machine's existing setup overrides anything here.

## Role
A Linux host running Docker for beta deploys and self-hosted services, reachable over Tailscale (see `tailscale.md`), designed to keep running unattended and come back by itself after a reboot or power loss.

## Resilience & auto-recovery (the point of an unattended box)
Five separate failure modes — handle each:

- **Don't sleep.** A suspended host is unreachable. `sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target`, and set the desktop environment to never auto-suspend/blank.
- **Auto-boot after power loss (the big one).** In BIOS/UEFI (Advanced → APM / Power Management), set *Restore on AC Power Loss* / *After Power Failure* → **Power On**. This is what boots the machine when power returns after an outage; nothing in software can substitute, because during the outage nothing is running.
- **Survive OS hangs.** Enable the hardware/systemd watchdog for hard freezes: in `/etc/systemd/system.conf`, `RuntimeWatchdogSec=20s` and `RebootWatchdogSec=10min`; also set `kernel.panic=10` (sysctl) to auto-reboot on a kernel panic.
- **Auto-start everything on boot.** Services as enabled systemd units; containers with `restart: unless-stopped`. Confirm `tailscaled` is enabled so the box rejoins the tailnet on boot without you.
- **Wake-on-LAN as a backstop.** For a box that's fully off, WoL boots it remotely — but a magic packet is layer-2, so Tailscale can't send it; you need a helper already on the LAN (e.g. an always-on NVR box) to relay it. Enable WoL in BIOS and in Linux (`ethtool ... wol g`, made persistent).

Optional but worth it: a small **UPS** with `nut`/`apcupsd` rides through flickers and gracefully shuts down on a long outage — after which BIOS auto-boot brings the box back when the UPS re-powers.

## Services & exposure
- Docker + Compose for services; `restart: unless-stopped`; a reverse proxy (Caddy/Traefik/nginx) for TLS and routing.
- Expose beta apps over Tailscale: **Serve** for tailnet-only HTTPS, **Funnel** for an authenticated public URL (client previews, or cloud-agent smoke tests). See `tailscale.md`.
- Keep durable data on named volumes; don't run the datastore as an ephemeral container without a persistence + backup plan.

## Backups
- Back up durable data **off-box** (another host, an object store) on a schedule, and **test the restore** — an untested backup is a hope, not a backup.
- Snapshot volumes before risky changes. Document the restore steps.

## Updates & patching
- Unattended security updates (`unattended-upgrades`) or a regular cadence; keep base images patched and re-pull.
- Reboot deliberately after kernel updates — auto-boot + auto-start means it comes back clean.

## Monitoring
- Uptime/health (e.g. Uptime Kuma) on the key services; host metrics (disk, memory, CPU, temperature); alert on disk-full, cert expiry, and service-down.
- Tailscale's admin console shows node online/offline at a glance.

## Security
- SSH via keys only, ideally Tailscale SSH (ACL-controlled, no public port). Non-root containers. Host firewall allowing only what's needed (lean on the tailnet rather than public ports).
- Least privilege for service accounts; don't run everything as root.

## Working from the road
Once a task is dispatched to a service here it runs independently of your connection; reach and operate the box over Tailscale from any device, and use Funnel-with-auth when a cloud agent (not on the tailnet) needs to reach a beta deploy.
