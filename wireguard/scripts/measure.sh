#!/bin/bash

initial=$(bash ../scripts/get_traffic.sh wg0)
initialArr=($initial)
initialRx=${initialArr[1]}

touch throughput.txt
> throughput.txt
while [ 1 ]   # Endless loop.
do
        current=$(bash ../scripts/get_traffic.sh wg0)
        currentArr=($current)
        currentRx=${currentArr[1]}
        echo $(($currentRx - $initialRx)) >> throughput.txt
        initialRx=$currentRx
        sleep 1
done