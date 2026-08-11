# Security

Please report suspected vulnerabilities through a private GitHub security
advisory rather than a public issue.

RTK Hermes Plus executes the locally installed `rtk` binary without `shell=True`.
It never stores terminal command strings in its own metrics. Native results are
written only when compression occurs and use bounded rotation. POSIX systems
enforce a `0700` recovery directory and `0600` files; Windows artifacts remain
inside the user's profile and inherit its Windows ACLs.

The optional experiment ledger stores session/turn identifiers, RTK mode,
model/provider labels, token/cost totals, transformation counts, and a salted
local SHA-256 fingerprint used to match repeated prompts across modes. It does
not store prompt text, commands, or tool contents and is never uploaded by the
plugin. The ledger lives in the same private `rtk-plus` directory, uses `0600`
on POSIX, and inherits the user's profile ACLs on Windows. Anyone who can read
the user's Hermes profile can still read its metadata; treat that profile as
sensitive local application data.

Remote terminal backends are disabled by default because both RTK and any local
file paths used by aggressive compression must exist in the execution backend.
