#python manager.py runserver --host=0.0.0.0 --port=8888
gunicorn -c gunicorn.py manager:app
