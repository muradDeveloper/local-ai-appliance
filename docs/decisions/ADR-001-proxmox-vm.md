# ADR-001: Use a Proxmox VM

**Status:** Accepted

## Context

The appliance requires NVIDIA drivers, CUDA-compatible container runtime support, durable backups and straightforward recovery. Previous homelab experience showed that Docker and NVIDIA device mapping inside LXC adds AppArmor, cgroup and permission complexity.

## Decision

Use a dedicated Ubuntu Server VM with full RTX 3060 PCIe passthrough.

## Consequences

- Cleaner GPU isolation and driver ownership.
- Easy PBS backup and VM-level recovery.
- GPU is dedicated to the VM while attached.
- Slightly higher overhead than LXC.
