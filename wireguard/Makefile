KEYS_DIR=key_store


all: full

full: build
	wg --version 

restart: dockerrm build
	docker run -dit --cap-add=NET_ADMIN --name=peer1 wg-peer1
	docker run -dit --cap-add=NET_ADMIN --name=server wg-server
	docker run -dit --cap-add=NET_ADMIN --name=server2 wg-server2
	docker run -dit --cap-add=NET_ADMIN --name=server3 wg-server2

brestart: dockerrm build
	docker run -dit --cap-add=NET_ADMIN --name=peer1 wg-peer1
	docker run -dit --cap-add=NET_ADMIN --name=server wg-server
	docker run -dit --cap-add=NET_ADMIN --name=server2 wg-server2
	docker run -dit --cap-add=NET_ADMIN --name=server3 wg-server2
	docker run -dit --cap-add=NET_ADMIN --name=server4 wg-server2
	docker run -dit --cap-add=NET_ADMIN --name=server5 wg-server2
	docker run -dit --cap-add=NET_ADMIN --name=server6 wg-server2

srestart: dockerrm
	docker run -dit --cap-add=NET_ADMIN --name=peer1 wg-peer1
	docker run -dit --cap-add=NET_ADMIN --name=server wg-server
	docker run -dit --cap-add=NET_ADMIN --name=server2 wg-server2

build:
	docker build -t wg-peer1 -f Peer1Dockerfile .
	docker build -t wg-server -f ServerDockerfile .
	docker build -t wg-server2 -f Server2Dockerfile .
	docker build -t nat-server -f NATDockerfile .

keys:
	wg genkey | tee ${KEYS_DIR}/peer1/privatekey | wg pubkey > ${KEYS_DIR}/peer1/publickey
	wg genkey | tee ${KEYS_DIR}/peer2/privatekey | wg pubkey > ${KEYS_DIR}/peer2/publickey
	wg genkey | tee ${KEYS_DIR}/server/privatekey | wg pubkey > ${KEYS_DIR}/server/publickey
	wg genkey | tee ${KEYS_DIR}/server2/privatekey | wg pubkey > ${KEYS_DIR}/server2/publickey

ready:
	cp ${KEYS_DIR}/${name}/wg0.conf /etc/wireguard/

upc:
	wg-quick up wg0
	python3 src/client.py

ups:
	wg-quick up wg0
	python3 src/server.py

mk:
	mkdir ./${BUILD_DIR}

dockerrm:
	-docker stop server
	-docker stop peer1
	-docker stop server2
	-docker stop server3
	-docker rm server peer1 server2 server3 server4 server5 server6 

rename:
	$(eval CC = clang++ -std=c++11 -pthread)

mac: rename ${OUTPUT_NAME}

install:
	sudo apt update
	sudo apt install libsdl2-dev

.PHONY: clean

clean:
	rm -rf ${BUILD_DIR}/ ./${OUTPUT_NAME}