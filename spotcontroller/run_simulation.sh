cd controller/

rm db.sqlite3

export RUN_MAIN=FALSE

python3 manage.py makemigrations
python3 manage.py migrate
python3 manage.py runscript run_simulation
