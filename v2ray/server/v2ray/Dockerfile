FROM v2fly/v2fly-core

EXPOSE 10086

COPY config.json /etc/v2ray/config.json

ENV v2ray.location.confdir=/etc/v2ray

ENTRYPOINT [ "/usr/bin/v2ray", "run" ]
