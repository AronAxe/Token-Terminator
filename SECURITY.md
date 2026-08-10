# Security

Please report suspected vulnerabilities through a private GitHub security
advisory rather than a public issue.

RTK Hermes Plus executes the locally installed `rtk` binary without `shell=True`.
It never stores terminal command strings in its own metrics. Native results are
written only when compression occurs, to an owner-only directory (`0700`) and
owner-only files (`0600`), with bounded rotation.

Remote terminal backends are disabled by default because both RTK and any local
file paths used by aggressive compression must exist in the execution backend.
