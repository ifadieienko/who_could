# Host security foundation

Who could keeps host security separate from the Docker deployment foundation:

```text
Internet
  -> CrowdSec firewall remediation (host INPUT + Docker DOCKER-USER)
  -> Docker published edge ports
  -> unprivileged Nginx
  -> non-root backend
```

`sudo ./server.sh security-install` explicitly installs/configures this layer.
Unattended application installation does not opt in to CrowdSec or enable UFW.

## CrowdSec architecture

The CrowdSec Security Engine runs as a host systemd service and consumes SSH
authentication events plus Nginx access records. The Linux and Nginx Hub
collections parse those events and produce decisions in the local API (LAPI).
The official firewall bouncer polls LAPI and enforces IP decisions. Engine and
bouncer are separate: a healthy engine alone does not prove remediation.

CrowdSec is installed from its official Debian/Ubuntu package repository without
pinning an obsolete release. The installer downloads the official bootstrap to
a file over verified HTTPS and checks that it identifies CrowdSec's package
repository before executing it; it does not use an unaccountable curl-to-shell
pipeline. See the [official Linux installation documentation](https://docs.crowdsec.net/u/getting_started/installation/linux/).

If `cscli` already exists, Who could records `CROWDSEC_PREEXISTING=true`, does
not reinstall CrowdSec, reset its database, or replace user acquisition files.
Only `who-could-*.yaml` files are managed. Collections are installed only when
missing and user collections are never removed. The installed version is
recorded root-only in `/opt/who-could/state/security/crowdsec_version`.

## Acquisition and the Docker socket

Nginx continues logging to Docker stdout. The host CrowdSec Docker datasource
matches a stable Compose web service name rather than a container ID, so
rebuild/recreate does not detach acquisition. The fixture at
`security/fixtures/nginx-access.log` uses Nginx combined format and can be
checked on a CrowdSec host with:

```bash
sudo cscli explain --type nginx --file deploy/security/fixtures/nginx-access.log
```

`security-install` runs this explanation after installing the Nginx collection
and refuses to continue unless the fixture is enriched by the Nginx parser.

The host CrowdSec service runs with its package-defined privileges. Docker log
acquisition requires that this privileged host service can reach Docker's Unix
socket. The installer inspects the systemd service user, verifies that identity
can read the socket, and fails if the socket is world-readable. It never makes it
world-readable and never mounts it
into web, backend, or database containers. If the host service cannot read it,
fix the host service's least-privilege group/access policy; do **not** use
`chmod 666 /var/run/docker.sock`.

SSH acquisition uses readable `/var/log/auth.log` when available, otherwise a
systemd journal filter for `ssh.service`/`sshd.service`. It never changes
`PasswordAuthentication`, `PermitRootLogin`, or `AllowUsers`.

Direct deployments retain Nginx's socket peer address. Arbitrary
`X-Forwarded-For` and `CF-Connecting-IP` are not trusted. CDN/trusted-proxy
support needs a separate design.

## Firewall model and Docker

Docker owns its NAT/firewall topology. Who could never flushes iptables/nftables,
never resets UFW, and never disables Docker's iptables/ip6tables management.
For Docker's iptables-compatible model, the bouncer is configured for `INPUT`
(host services such as SSH) and `DOCKER-USER` (forwarded published-port traffic).
The existing chain is required; no duplicate jump/rule is created by Who could.
See Docker's [packet filtering and DOCKER-USER documentation](https://docs.docker.com/engine/network/packet-filtering-firewalls/).

IPv4 and IPv6 chains are configured independently. IPv4 requires `INPUT` and
`DOCKER-USER`. IPv6 always protects host `INPUT`; Docker `DOCKER-USER` is added
only when the real ip6tables chain exists. If the web container has a public
IPv6 binding but that rule/set path cannot be verified, installation and tests
fail closed. Status reports IPv4 and IPv6 separately; IPv6 is `DISABLED` only
when no public Docker IPv6 binding is detected.

The package bouncer unit receives a Who could-namespaced systemd drop-in with
`Wants=docker.service` and `After=docker.service`. Its pre-start helper waits at
most 30 seconds for Docker to create the IPv4 `DOCKER-USER` chain. This preserves
remediation after reboot without editing the package unit. Removal deletes only
this drop-in/helper and reloads systemd.

Docker's native nftables backend has a different forwarding topology and no
DOCKER-USER equivalent. This release intentionally fails closed with:

> Docker native nftables web-port remediation is not automatically configured
> by this version.

It does not claim Docker web protection or synthesize an unverified nftables
topology. A diagnostic snapshot of available UFW, iptables, and nftables state
is captured before the first managed firewall operation; it is not an automatic
restore script.

## UFW and SSH safety

UFW INPUT rules and Docker published-port filtering are reported separately:
ordinary UFW rules alone are not proof that Docker ports are protected. If UFW
is already active, Who could adds only identified allow rules and preserves all
existing rules. If inactive, interactive setup asks:

```text
UFW is currently disabled. Enable host firewall? [y/N]
```

The default is **No**, and non-interactive setup never enables it. Before an
enable, the effective SSH port is obtained with `sshd -T`, validated, and
allowed first; HTTP and enabled HTTPS are allowed next, then UFW is enabled.
Removal never deletes the SSH safety rule, resets, or disables UFW.
It removes only HTTP/HTTPS rules that this installer recorded with its exact
managed comments; equivalent operator rules are left alone. When UFW is already
active, its existing SSH policy is never broadened or rewritten.

## Commands

* `sudo ./server.sh security-install` — idempotently install collections,
  namespaced acquisition and the official firewall bouncer, then test it.
* `sudo ./server.sh security-test` — verify engine/LAPI/acquisition/bouncer and
  create a two-minute decision only for TEST-NET `192.0.2.1`. A trap always
  removes it; when IPv6 remediation is active it similarly uses only
  `2001:db8::1`. The current SSH client, loopback and public host IP are never used.
* `sudo ./server.sh security-status` — show engine, collections, acquisition,
  decisions, bouncer, Docker integration, UFW and SSH port without API keys.
* `sudo ./server.sh security-remove` — remove only Who could acquisition and
  override files. It preserves application data, secrets, certificates,
  databases, packages, user CrowdSec configuration and host firewall state.
  When Who could originally installed the retained bouncer package, removal
  disables its service but deliberately keeps the matching base config/API key
  and LAPI registration so a later `security-install` can safely re-enable it.
* `./deploy/test_host_security_acceptance.sh` — dry-run unless the explicit
  `--i-understand-this-modifies-firewall` flag is supplied on a disposable VM.
  The prepare phase tests repeated installation; after reboot, `--post-reboot`
  verifies Docker/engine/bouncer ordering, real remediation, cleanup and removal.

State-changing application and security commands share
`/opt/who-could/state/server.lock`. Existing version-1 configuration is migrated
atomically to version 2, retaining database mode, ports, hostname, TLS and image
settings while adding safe disabled security defaults.

## Troubleshooting

Run `sudo ./server.sh security-status`, `./server.sh doctor`, `systemctl status
crowdsec crowdsec-firewall-bouncer`, `cscli metrics`, and `cscli bouncers list`.
Inspect `/etc/crowdsec/acquis.d/who-could-*.yaml` and the root-only diagnostic
snapshot under `/opt/who-could/state/security`. API keys are intentionally not
printed or stored in deployment configuration.

## Explicit limitations

This layer provides behavioral detection, IP-level firewall remediation,
SSH/infrastructure protection, and Nginx log analysis. It is **not** a complete
request-level WAF: CrowdSec AppSec and an Nginx Lua bouncer are not enabled, and
no claim is made that all web attacks are blocked. A future AppSec PR requires
either a Lua-enabled Nginx build or an OpenResty migration plus full edge-proxy
regression testing. This release also has no trusted CDN/proxy support and no
update/rollback command.
