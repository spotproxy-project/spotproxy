
SERVER="3.91.73.130"
VER="5"
STATE="with"
TESTTYPE="kv"

# scp -i ~/.ssh/nv-usa-test-umich.pem ubuntu@$SERVER:client-folder/hush-proxy/src/throughput.txt results/resv2/throughput$VER-$STATE-mig-$TESTTYPE-old-script.txt
scp -i ~/.ssh/nv-usa-test-umich.pem ubuntu@$SERVER:client-folder/hush-proxy/src/throughput_p_i.txt results/resv2/throughput$VER-$STATE-mig-$TESTTYPE-p-in.txt
# scp -i ~/.ssh/nv-usa-test-umich.pem ubuntu@$SERVER:client-folder/hush-proxy/src/throughput_p_o.txt results/resv2/throughput$VER-$STATE-mig-$TESTTYPE-p-out.txt