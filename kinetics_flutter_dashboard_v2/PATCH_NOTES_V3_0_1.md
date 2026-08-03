# Kinetics Flutter V3.0.2 reliability patch

- Tracks asynchronous automatic runs independently per pair.
- Polls the accepted pair-specific cached status endpoint every 2 seconds.
- Prevents an older all-pair cache snapshot from overwriting a newer pair status.
- Keeps pair selection available while another pair is starting/running.
- Stores latest gateway response per pair.
- Reduces global diagnostics polling from 8 s to 30 s.
- Updates production precharge wording to BAU 0x3001.
