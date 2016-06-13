# -*- coding: utf-8 -*-
from datetime import datetime
from flask_login import UserMixin
from . import db,login_manager
from collections import namedtuple
info = {"result":True,"errorMsg":None}

@login_manager.user_loader
def load_user(user_id):
    return User.query.filter_by(id=user_id).first()

login_manager.session_protection = "strong"
login_manager.login_view = "main.login"
login_manager.login_message = {"type":"error","message":"请登录后使用该功能"}

# class User(db.Model,UserMixin):
#     id = db.Column(db.Integer,primary_key=True)
#     nickname = db.Column(db.String(32))
#     sex = db.Column(db.String(10))
#     phonenum = db.Column(db.String(32),unique=True,index=True)
#     email = db.Column(db.String(32),unique=True,index=True)
#     password = db.Column(db.String(128))
#     password_heihei = db.Column(db.String(2048))
#     ip = db.Column(db.String(32))
#     apis = db.relationship('Api', backref='user', lazy='dynamic')
#     suits = db.relationship('TestSuit', backref='user', lazy='dynamic')
#     cases = db.relationship('ApiCase', backref='user', lazy='dynamic')
#     createdtime = db.Column(db.DateTime,default=datetime.now)
#
#     def __init__(self,nickname,phonenum,password,password_heihei,email,sex,ip):
#         self.nickname = nickname
#         self.phonenum = phonenum
#         self.email = email
#         self.password = password
#         self.password_heihei = password_heihei
#         self.sex = sex
#         self.ip = ip
#
#     def __repr__(self):
#         return "<User:%s>" %self.nickname

class Mission(db.Model):
    id = db.Column(db.Integer,primary_key=True)
    name = db.Column(db.String(32))
    urls = db.Column(db.PickleType)
    types = db.Column(db.PickleType)
    concurrent = db.Column(db.Integer)
    looptime = db.Column(db.Integer)
    looptimetype = db.Column(db.Integer)
    createdtime = db.Column(db.DateTime, default=datetime.now)

    def __init__(self,name,urls,types,machines,concurrent,looptime,looptimetype):
        self.name = name.strip()
        self.urls = urls
        self.types = types
        self.machineids = [int(m) for m in machines]
        self.concurrent = concurrent
        self.looptime = int(looptime)
        self.looptimetype = int(looptimetype)

    @property
    def machines(self):
        return [Machine.query.filter_by(id=id).first() for id in self.machineids]

    @property
    def fakeMachines(self):
        fakemachines = []
        machines = self.machines
        for machine in machines:
            fakemachine = namedtuple("Machine","name ip system sshtype user port password rsa")
            fakemachine.name = machine.name
            fakemachine.ip = machine.ip
            fakemachine.system = machine.system
            fakemachine.sshtype = machine.sshtype
            fakemachine.user = machine.user
            fakemachine.port = machine.port
            fakemachine.password = machine.password
            fakemachine.rsa = machine.rsa
            fakemachines.append(fakemachine)

        return fakemachines

    def __repr__(self):
        return "<Mission:%s>" % self.name

class Machine(db.Model):
    id = db.Column(db.Integer,primary_key=True)
    name = db.Column(db.String(32))
    ip = db.Column(db.String(64))
    system = db.Column(db.String(32))
    sshtype = db.Column(db.String(16))
    user = db.Column(db.String(32))
    port = db.Column(db.Integer)
    password = db.Column(db.String(32))
    rsa = db.Column(db.String(5000))
    memory = db.Column(db.String(20))
    cpu = db.Column(db.Integer)
    disk = db.Column(db.String(20))
    createdtime = db.Column(db.DateTime,default=datetime.now)

    def __init__(self,name,ip=None,system=None,sshtype=None,user=None,port=None,password=None,rsa=None,memory=None,cpu=None,disk=None):
        self.name = name
        self.ip = ip
        self.system = system
        self.sshtype = sshtype
        self.user = user
        self.port = port
        self.password = password
        self.rsa = rsa
        self.memory = memory
        self.cpu = cpu
        self.disk = disk

    def __repr__(self):
        return "<Machine:%s>" % self.name