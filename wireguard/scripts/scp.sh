#!/bin/bash

trap trapint 2
function trapint {
    exit 0
}

(
        bash measure.sh
) &

tt=${1:-300}
for (( c=1; c<=$tt; c++ )) do
        scp -i ~/.ssh/spotproxy-keys/nv-usa-test-umich.pem ubuntu@3.80.71.88:/tmp/random.img /tmp/random.img
        sleep 0.1
done

kill $(jobs -p)