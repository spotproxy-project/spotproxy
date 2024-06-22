#!/bin/bash

(
        bash measure.sh
) &

tt=${1:-300}
for (( c=1; c<=$tt; c++ )) do
        curlReq=$(curl --silent https://www.wikipedia.org)
        echo $curlReq
        echo "Next iteration.."
        sleep 0.1
done

kill $(jobs -p)