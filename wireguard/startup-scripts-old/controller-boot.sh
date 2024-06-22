#!/bin/bash

git clone https://github.com/johnsinak/hush-controller.git

cd hush-controller/controller/
python3 manage.py migrate

python3 manage.py runserver 0.0.0.0:8000
