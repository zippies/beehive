# -*- coding: utf-8 -*-
import os,platform

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
    redis_db = os.environ.get("REDIS_DB")

    nsq_host = os.environ.get("NSQ_HOST")

    client_path = os.path.join(os.path.dirname(__file__),"clienthive")


    @staticmethod
    def init_app(app):
        pass

    @property
    def system(self):
        return platform.system().lower()
    
    @property
    def localip(self):
        ip = None
        if self.system == "windows":
            cmd = "ipconfig|findstr IPv4"
            ip = os.popen(cmd).read().split(":")[1].strip()
        else:
            cmd = "ifconfig|grep netmask"
            ip = os.popen(cmd).read().split("netmask")[0].split("inet")[1].strip()
        return ip
    
    @property
    def disk(self):
        disk = None
        if self.system == "windows":
            pass
        else:
            cmd = "df -m"
            disk = [i.strip() for i in os.popen(cmd).readlines()[1].split(" ") if i.strip()][1]
        return "%sM" %disk
    
    @property
    def memory(self):
        m = None
        if self.system == "windows":
            pass
        else:
            cmd = "free -m"
            m = [i.strip() for i in os.popen(cmd).readlines()[1].split(" ") if i.strip()][1]
        return "%sM" %m
    