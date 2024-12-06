FROM python:3

WORKDIR /opt/spotproxy-v2ray

COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt

RUN git clone --depth=1 https://github.com/v2fly/v2ray-core.git
RUN find v2ray-core/ -name '*.proto' -exec python -m grpc_tools.protoc -Iv2ray-core --python_out=. --pyi_out=. --grpc_python_out=. {} +

COPY client_manager.py client_manager.py

CMD ["python", "client_manager.py"]
