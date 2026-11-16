# Example: what the context explorers write

Copy this folder to `central/docs/context/understanding/` (the tests do) and run
`baton context understand`. Billing comes out `understood`; pricing comes out `blocked`, because six of its
branch points have no confirmed rule and only the Product Owner can name one. The landscape is `understood`:
the Tech Lead answered who is on the other side of `invoices` and `prices`. So `baton context check F-001`,
which changes billing, is accepted, and a feature that changes pricing is not.
