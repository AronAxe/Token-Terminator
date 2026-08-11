# Security

Please report suspected vulnerabilities through a private GitHub security
advisory rather than a public issue.

RTK Hermes Plus executes the locally installed `rtk` binary without `shell=True`.
It never stores terminal command strings in its own metrics. Native results are
written only when compression occurs and use bounded rotation. POSIX systems
enforce a `0700` recovery directory and `0600` files; Windows artifacts remain
inside the user's profile and inherit its Windows ACLs.

Remote terminal backends are disabled by default because both RTK and any local
file paths used by aggressive compression must exist in the execution backend.
