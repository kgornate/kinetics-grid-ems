# Kinetics Flutter Dashboard V2.2

- Fixed Windows debug render assertion in the rack Cells tab by replacing the nested PaginatedDataTable layout with a stable paged table.
- Automatically requests complete rack arrays when a rack detail page opens and the arrays are missing.
- Added visible loading, retry, and error states for rack-detail extraction.
- Increased rack-detail API timeout to five minutes.
- Increased metric-card height to remove bottom-overflow warnings on dashboard cards.
- No gateway/backend change is required for this Flutter cell-view fix.
