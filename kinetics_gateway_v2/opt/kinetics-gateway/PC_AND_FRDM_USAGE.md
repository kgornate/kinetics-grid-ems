# PC and FRDM Usage

## Update the PC working copy

Do not overlay this archive blindly onto your only copy. First rename or back up the existing PC folder. Then extract this archive and use its `backend` directory as the new cumulative backend working copy.

Example PowerShell flow:

```powershell
cd C:\Users\KunalGupta\EMS_Ornte_Code_base\kinetics-grid-ems

Rename-Item `
  .\imx93_gateway\backend `
  .\imx93_gateway\backend_before_phase1_6

tar -xzf `
  .\Kinetics_Gateway_Consolidated_Baseline_Phase1_6_20260805.tar.gz

Copy-Item `
  -Recurse `
  .\Kinetics_Gateway_Consolidated_Baseline_Phase1_6_20260805\backend `
  .\imx93_gateway\backend
```

Adjust the parent path if this Kinetics codebase is stored elsewhere. Keep the extracted consolidated folder as a versioned recovery copy.

## Recommended Git checkpoint on PC

From the repository root:

```powershell
git status
git add imx93_gateway/backend
git commit -m "Consolidate Kinetics gateway through Phase 1.6"
```

Review `git status` before committing so unrelated local work is not added accidentally.

## FRDM: preferred current-board method

Your existing FRDM has already received the phases incrementally. Do not reinstall the entire backend merely to make it consolidated. Complete the Phase 1.6 validation using:

```text
phase_docs/PHASE1_6_FRDM_VALIDATION.md
```

## FRDM: recovery or new-board method

This source baseline can rebuild `/opt/kinetics-gateway/backend`, but it intentionally does not include the board-specific `/etc/kinetics-gateway/config.json`, environment file, Python virtual environment, database, or credentials. Back up and restore those separately.

Before replacing any backend on a board:

```bash
systemctl disable --now bess-seven-day-v302.service
systemctl stop kinetics-gateway.service

BACKUP="/root/kinetics_backend_before_phase1_6_$(date +%Y%m%d_%H%M%S)"
cp -a /opt/kinetics-gateway/backend "$BACKUP"
printf '%s\n' "$BACKUP"
```

Copy and extract the archive:

```powershell
scp .\Kinetics_Gateway_Consolidated_Baseline_Phase1_6_20260805.tar.gz root@192.168.10.2:/root/
```

```bash
mkdir -p /root/kinetics_phase1_6_consolidated

tar -xzf \
  /root/Kinetics_Gateway_Consolidated_Baseline_Phase1_6_20260805.tar.gz \
  -C /root/kinetics_phase1_6_consolidated
```

For a recovery/new-board installation, copy the extracted `backend` tree only after checking that the deployed `/etc/kinetics-gateway` configuration and virtual environment are intact. Then run the complete Phase 1.6 validation guide before considering the baseline approved.

## Important scheduler rule

The `legacy_scheduler_reference` directory is included for source preservation only. Do not copy it into a running service or enable `bess-seven-day-v302.service` during Phase 1. The later modular architecture will migrate scheduling behavior through the gateway-owned orchestration path.
