<!--
library: tailscale
versions-covered: "1.x"
last-verified: 2026-07-09
provenance: manual
sources:
  - https://tailscale.com/kb
-->

# Tailscale conventions

The private network that ties the firm together — home box, cloud hosts, and your devices on one tailnet. Read after choosing to wire networking/access with Tailscale. Existing tailnet config overrides anything here.

## Core
- `tailscale up` joins a device to the tailnet; **MagicDNS** gives every node a stable name (e.g. `homeserver`) — use names, not IPs.
- The tailnet is the private network; prefer reaching services over it instead of opening public ports.

## Key expiry (do this for servers)
- **Disable key expiry on always-on nodes** (a home server, cloud hosts) in the admin console. Otherwise the key lapses on a schedule and the box silently drops off the tailnet — and if you're on the road, you're locked out. This is the single most common self-inflicted outage.

## Access control (ACLs)
- Define ACLs to scope who/what reaches what; **tag** devices (`tag:server`, `tag:beta`) and grant by tag rather than by individual node. Least privilege — a client device shouldn't reach admin surfaces.
- Review ACLs when adding nodes or exposing new services.

## Exposing services: Serve vs Funnel
- **Serve** — publishes a local service as HTTPS **within the tailnet** (clean names, valid certs, no public exposure). The default for beta/dev access for yourself.
- **Funnel** — publishes a service to the **public internet** over HTTPS. Use with authentication for client previews or when a **cloud agent that isn't on the tailnet** needs to reach a beta deploy (e.g. pipeline smoke tests). Scope it tightly and turn it off when done.

## SSH
- **Tailscale SSH** authenticates SSH over the tailnet with ACL control — no exposed SSH port, no separate key distribution. Prefer it for host access.

## Routing
- **Subnet routes** expose a whole LAN subnet to the tailnet (reach devices that can't run Tailscale). **Exit nodes** route a device's traffic through another node when needed. Enable deliberately; both widen the trust surface.

## Wake-on-LAN caveat
- Tailscale **cannot** send a Wake-on-LAN magic packet — WoL is layer-2 and Tailscale operates above it. To wake a powered-off box remotely, SSH into a helper node already on the same LAN and send the packet from there (see `home-infra.md`).

## Security hygiene
- Authorize new devices deliberately; rotate keys; review the device list and ACLs periodically. Treat the tailnet as private infrastructure, not a public network.
