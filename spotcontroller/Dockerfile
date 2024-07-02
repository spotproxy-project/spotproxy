FROM python:3.11-slim-bookworm
RUN apt update && apt install make -y
COPY . /
RUN pip install -r /requirements.txt
RUN python controller/manage.py makemigrations
RUN python controller/manage.py migrate

ENV DJANGO_SUPERUSER_PASSWORD=123
RUN python controller/manage.py createsuperuser --username admintest --email abc@abc.com --noinput

CMD python controller/manage.py runserver 0.0.0.0:8000
