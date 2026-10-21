# Complete Codebase Notice

Every `Ornate_EMS_Gateway_Elecod_Lineage_PhaseX_*.zip` release produced in this migration is intended as a **complete gateway source tree**, not a paste-in patch bundle.

For Phase 4:

- Extract/use the whole archive as the application tree.
- Do not manually copy individual Python patches into the old Kinetics deployment.
- The original Kinetics files are intentionally retained where still part of the frozen architecture.
- Historical `.patch`, old validation documents and Kinetics deployment helpers inside the tree are reference artifacts; the Phase-4 deployment entry points are explicitly named `phase4` / `ornate-ems-gateway`.

The safe operating model is:

```text
complete Phase-4 codebase
        +
site-specific config.json
        +
read-only commissioning
```

not:

```text
old production tree + manual copy/paste of random changed files
```
