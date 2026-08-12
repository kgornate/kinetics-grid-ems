# Phase F3.1 - Historian Export Final Patch

This patch is intended to be applied on top of the working Phase F2 persistent-navigation app.

It includes:

- Phase F2 Historian screen
- Phase F2 persistent navigation support
- Removal of the old inline ExpansionTile/FilterChip selector that caused the red runtime error
- Safe dialog-based PCS/BMS parameter selector
- CSV export of currently loaded historian rows
- Excel .xlsx export of currently loaded historian rows
- Visible export buttons in both the filter action row and the History Table header
- Download helpers for Windows/desktop and web

Important: this is Flutter-side export for the currently loaded filtered table only. Full 7/30/90-day raw exports should be implemented later as backend/server-side export.

Validation strings after applying:

- fast_bess_historian_screen.dart must contain `Download CSV`
- fast_bess_historian_screen.dart must contain `Download Excel`
- fast_bess_historian_screen.dart must NOT contain `Download/export will be added in Phase F3`
- fast_bess_historian_screen.dart must NOT contain `ExpansionTile`
- fast_bess_historian_screen.dart must NOT contain `FilterChip`
