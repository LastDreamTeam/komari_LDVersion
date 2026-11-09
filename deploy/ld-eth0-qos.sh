#!/bin/bash
# LastDream eth0 anti-saturation QoS for Komari/SSH vs proxy
# - Remove accidental netem
# - CAKE 800mbit egress + IFB ingress
# - DSCP: SSH/EF, nginx:80/443 AF41, xray direct ports CS1 (bulk under load)
set -euo pipefail
IFACE=eth0
BW=800mbit
XRAY_PORTS=(8443 43220 46444 37125 42267)

modprobe sch_cake 2>/dev/null || true
modprobe ifb 2>/dev/null || true
modprobe act_mirred 2>/dev/null || true

# clear existing
tc qdisc del dev "$IFACE" root 2>/dev/null || true
tc qdisc del dev "$IFACE" ingress 2>/dev/null || true
ip link del ifb0 2>/dev/null || true

# egress CAKE
tc qdisc add dev "$IFACE" root cake bandwidth "$BW" diffserv3 nat dual-srchost ack-filter

# ingress via IFB
ip link add ifb0 type ifb
ip link set ifb0 up
tc qdisc add dev "$IFACE" handle ffff: ingress
tc filter add dev "$IFACE" parent ffff: protocol all u32 match u32 0 0 action mirred egress redirect dev ifb0
tc qdisc add dev ifb0 root cake bandwidth "$BW" diffserv3 nat dual-dsthost ingress

# DSCP marks (egress classification for CAKE tins)
# flush previous ld-qos chain if re-run
if command -v iptables >/dev/null; then
  iptables -t mangle -D OUTPUT -j LD-QOS 2>/dev/null || true
  iptables -t mangle -F LD-QOS 2>/dev/null || true
  iptables -t mangle -X LD-QOS 2>/dev/null || true
  iptables -t mangle -N LD-QOS
  iptables -t mangle -A LD-QOS -p tcp --sport 22 -j DSCP --set-dscp-class EF
  iptables -t mangle -A LD-QOS -p tcp --sport 80 -j DSCP --set-dscp-class AF41
  iptables -t mangle -A LD-QOS -p tcp --sport 443 -j DSCP --set-dscp-class AF41
  for p in "${XRAY_PORTS[@]}"; do
    iptables -t mangle -A LD-QOS -p tcp --sport "$p" -j DSCP --set-dscp-class CS1
    iptables -t mangle -A LD-QOS -p udp --sport "$p" -j DSCP --set-dscp-class CS1
  done
  iptables -t mangle -A OUTPUT -j LD-QOS

  ip6tables -t mangle -D OUTPUT -j LD-QOS 2>/dev/null || true
  ip6tables -t mangle -F LD-QOS 2>/dev/null || true
  ip6tables -t mangle -X LD-QOS 2>/dev/null || true
  ip6tables -t mangle -N LD-QOS 2>/dev/null || true
  ip6tables -t mangle -A LD-QOS -p tcp --sport 22 -j DSCP --set-dscp-class EF 2>/dev/null || true
  ip6tables -t mangle -A LD-QOS -p tcp --sport 80 -j DSCP --set-dscp-class AF41 2>/dev/null || true
  ip6tables -t mangle -A LD-QOS -p tcp --sport 443 -j DSCP --set-dscp-class AF41 2>/dev/null || true
  for p in "${XRAY_PORTS[@]}"; do
    ip6tables -t mangle -A LD-QOS -p tcp --sport "$p" -j DSCP --set-dscp-class CS1 2>/dev/null || true
    ip6tables -t mangle -A LD-QOS -p udp --sport "$p" -j DSCP --set-dscp-class CS1 2>/dev/null || true
  done
  ip6tables -t mangle -A OUTPUT -j LD-QOS 2>/dev/null || true
fi

# Extra: soft police on xray egress sports via HTB is incompatible with cake root.
# Rely on CS1 bulk tin + 800mbit ceiling. Documented in /opt/komari/QOS.txt

echo "ld-eth0-qos: applied CAKE $BW on $IFACE (+ifb0 ingress), netem cleared"
tc -s qdisc show dev "$IFACE" | head -20
tc -s qdisc show dev ifb0 | head -10
