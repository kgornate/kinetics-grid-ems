# Protocol Notes

The uploaded EMS protocol sheet defines the north-bound register table.

Known from the sheet:

- Port: 515
- Device/unit ID: 1
- Register quantity: 2
- Point type: Float
- Register range: 0 to 2840

Site/vendor confirmation required:

- EMS local IP address
- subnet and route details
- physical Ethernet port that exposes north-bound protocol
- holding vs input register function code
- float byte/word order: ABCD, CDAB, BADC, or DCBA
- firewall or whitelist requirements
