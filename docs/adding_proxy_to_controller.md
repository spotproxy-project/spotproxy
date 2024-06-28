This file will outline how to add a proxy to the controller using our endpoints.
## Adding a proxy to a running controller

1. The controller should be running following the steps in [docs/controller_setup.md](https://github.com/spotproxy-project/spotproxy/blob/main/docs/controller_setup.md)

2. Send a request to the running controller at this endpoint: ```<controller_endpoint>/assignments/postsingleupdate``` using HTTP ```POST``` and include the following in the body:

```JSON
"new_ips": ["<proxy_to_be_added_ip>"]
```

3. if you receive a HTTP 200 OK response, your proxy was successfully added to the controller.
