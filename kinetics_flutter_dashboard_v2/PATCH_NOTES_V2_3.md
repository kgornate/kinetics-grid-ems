# Kinetics Flutter Dashboard V2.3 - Material and view stability fix

## Fixed

- Fixed `No Material widget found` when opening or scrolling the BAU page.
- Fixed the same latent issue in environment asset details and the generic asset telemetry view.
- Wrapped all standalone `ExpansionTile` widgets in `Card`/Material surfaces.
- Adjusted expansion-body padding so the embedded engineering tables remain aligned.

## Root cause

`ExpansionTile` internally builds `ListTile` widgets. Three screens placed standalone
`ExpansionTile` widgets directly inside `ListView` content without a local Material ancestor.
When those tiles entered the render tree, Flutter raised:

`No Material widget found. ListTile widgets require a Material widget ancestor.`

The BAU page exposed the issue first at the "All BAU points" section. The same code pattern
also existed in:

- Environment asset details: "All asset points"
- Generic asset telemetry: "All signals"

Rack sensor sections and diagnostics already used `Card(child: ExpansionTile(...))` and did
not require this correction.

## Upgrade note

Use a full application restart after updating. A hot reload can preserve the invalid old
Element tree and make the error appear to remain until the process is restarted.
