#!/usr/bin/env bash
set -Eeuo pipefail

# Docker creates its chains asynchronously during daemon startup. Wait for IPv4
# always and IPv6 only when the managed bouncer config includes that chain.
config=${WHO_COULD_BOUNCER_CONFIG:-/etc/crowdsec/bouncers/crowdsec-firewall-bouncer.yaml.local}
need_ipv6=false
if [[ -r "$config" ]] && awk '
  /^iptables_v6_chains:/ { section=1; next }
  /^[^[:space:]#]/ { section=0 }
  section && /^[[:space:]]*-[[:space:]]*DOCKER-USER[[:space:]]*$/ { found=1 }
  END { exit !found }
' "$config"; then need_ipv6=true; fi

for _ in {1..30}; do
  ipv4_ready=false; ipv6_ready=true
  if iptables -w -nL DOCKER-USER >/dev/null 2>&1; then ipv4_ready=true; fi
  if $need_ipv6 && ! ip6tables -w -nL DOCKER-USER >/dev/null 2>&1; then ipv6_ready=false; fi
  if $ipv4_ready && $ipv6_ready; then exit 0; fi
  sleep 1
done
printf 'Timed out waiting 30 seconds for required Docker DOCKER-USER chain(s)\n' >&2
exit 1
