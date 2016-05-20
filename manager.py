# -*- coding: utf-8 -*-
from app import createApp,db
from app.models import Machine
from flask.ext.script import Manager,Shell
from flask.ext.migrate import Migrate,MigrateCommand
from werkzeug.contrib.fixers import ProxyFix
import multiprocessing,platform

app = createApp()
app.debug = True
app.wsgi_app = ProxyFix(app.wsgi_app)
manager = Manager(app)
migrate = Migrate(app,db)
manager.add_command('db',MigrateCommand)

@manager.command
def dbinit():
	db.create_all()
	machine = Machine("本机")
	machine.ip = "127.0.0.1"
	machine.cpu = multiprocessing.cpu_count()
	machine.system = platform.system().lower()
	machine.disk = "450G"
	machine.memory = "4G"
	db.session.add(machine)
	db.session.commit()
	print('dbinit ok')

@manager.command
def dbdrop():
	db.drop_all()
	print('ok')

if __name__ == '__main__':
	manager.run()