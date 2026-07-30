#!/usr/bin/env bash
# Run once on the VM after the stack is up.
# Applies kernel parameter tweaks and other one-time OS-level fixes.
set -Eeuo pipefail

echo "==> Applying kernel parameter: vm.overcommit_memory=1 (fixes Valkey/Redis warning)"
if grep -q 'vm.overcommit_memory' /etc/sysctl.conf; then
  echo "    Already set in /etc/sysctl.conf, skipping."
else
  echo 'vm.overcommit_memory = 1' | sudo tee -a /etc/sysctl.conf
fi
sudo sysctl vm.overcommit_memory=1

echo "==> Post-deployment steps complete."
