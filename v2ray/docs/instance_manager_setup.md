# Instance manager setup for V2Ray proxies

Setup is overall extremely similar to [../../docs/instance_manager_setup.md](../../docs/instance_manager_setup.md), with just a few differences detailed here.

## Initiate the instance manager

<!-- markdownlint-disable MD029 -->

1. Within your AWS account EC2 `Launch Templates` menu, create a new launch template:

   5. Under `Advanced details`, within the `User data` option: paste the text within `v2ray/server/proxy-boot.sh` file, with the `git clone` command optionally modified to point at a repo and branch with the desired implementation

<!-- prettier-ignore begin -->

3. Within the VM: modify the file `instance_manager/input-args-v2ray.json`: "launch-template" field to use the ID obtained above, "controller-IP" field to be the controller's IP address

   1. Within the VM: modify the file `instance_manager/api.py`: invoke `use_v2ray_launch_templates` instead of `use_jinyu_launch_templates` in `RequestHandler.do_GET`

<!-- prettier-ignore end -->

<!-- markdownlint-enable MD029 -->

## Artifact evaluation Experiment E1 Minimal working example

Use this command instead to run the instance manager:

```bash
python3 api.py input-args-v2ray.json simple-test
```

Once an instance is created, feel free to `nmap -p10086` it to see for yourself that the proxy is listening for connections.

## Artifact evaluation Experiment E3 Minimal working example

Use this command instead to run the instance manager:

```bash
python3 api.py input-args-v2ray.json
```
