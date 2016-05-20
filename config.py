# -*- coding: utf-8 -*-
import os

class Config:
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(os.path.abspath(os.path.dirname(__file__)),'data.sqlite')
    SECRET_KEY = 'what does the fox say?'
    WTF_CSRF_SECRET_KEY = "whatever"
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__),"app/static")
    SQLALCHEMY_TRACK_MODIFICATIONS = True
    log_path = os.path.join(os.path.dirname(__file__),"logs")

    redis_host = os.environ.get("REDIS_HOST")
    redis_port = os.environ.get("REDIS_PORT")
    redis_user = os.environ.get("REDIS_USER")
    redis_password = os.environ.get("REDIS_PASSWORD")
    redis_db = os.environ.get("REDIS_DB")

    client_path = os.path.join(os.path.dirname(__file__),"clienthive")
    nsq_addr = "104.236.5.165:4150"
    redis_addr = "104.236.16.75:6379"

    @staticmethod
    def init_app(app):
        pass
