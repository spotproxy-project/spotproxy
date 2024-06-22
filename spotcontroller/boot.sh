pip install -r requirements.txt

export RUN_MAIN=TRUE

cd controller
python3 manage.py makemigrations
python3 manage.py migrate
python3 manage.py runserver 0.0.0.0:8000
