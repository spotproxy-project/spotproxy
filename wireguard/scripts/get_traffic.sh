#!/bin/bash
# SECTION: Get current total traffic in and out of a particular network interface (specified in $1)
# Note: another approach we can take is to read from iftop as a text file format: https://unix.stackexchange.com/questions/20965/how-should-i-determine-the-current-network-utilization
_die() {
    printf '%s\n' "$@"
    exit 1
}

if [ $# -eq 0 ]
  then
    _die 'Usage: ifspeed [interface]'
fi

for _interface in "$@"
do
    _interface_bytes_in=$(awk "/^ *${_interface}:/"' { if ($1 ~ /.*:[0-9][0-9]*/) { sub(/^.*:/, "") ; print $1 } else { print $2 } }' /proc/net/dev)
    _interface_bytes_out=$(awk "/^ *${_interface}:/"' { if ($1 ~ /.*:[0-9][0-9]*/) { print $9 } else { print $10 } }' /proc/net/dev)

    _interfaces_pkts_in=$(cat /sys/class/net/$_interface/statistics/rx_packets)
    _interfaces_pkts_out=$(cat /sys/class/net/$_interface/statistics/tx_packets)

    printf '%s %s %s %s %s\n' $_interface $_interface_bytes_in $_interface_bytes_out $_interfaces_pkts_in $_interfaces_pkts_out
done

# printf '%s: %s\n' 'Kilobytes in/sec'  "$(( ( _interface_bytes_in_new - _interface_bytes_in_old ) / 1024 ))" \
#                   'Kilobytes out/sec' "$(( ( _interface_bytes_out_new - _interface_bytes_out_old ) / 1024 ))"

# printf '%s: %s\n' 'Megabits in/sec'  "$(( ( _interface_bytes_in_new - _interface_bytes_in_old ) / 131072 ))" \
#                   'Megabits out/sec' "$(( ( _interface_bytes_out_new - _interface_bytes_out_old ) / 131072 ))"