# -*- coding: utf-8 -*-
from flask import render_template,request,jsonify,Response,g
from ..models import db,Mission,info,Machine
from .queenBee import QueenBee,StatusController
from multiprocessing import Manager
from . import url
from config import Config
import json,time,redis

statusController = StatusController()
config = Config()

@url.route("/")
@url.route("/missions")
def missions():
    return render_template("missions.html",choiced="missions")

@url.route("/newmission",methods=["GET","POST"])
def newMission():
    timenow = time.strftime("%Y-%m-%d %H:%M:%S")
    if request.method == "POST":
        try:
            choicedmachines = dict(request.form).get("choicedMachine")
            print("choicedmachine",choicedmachines)
            mission = Mission(
                request.form.get("missionName"),
                request.form.get("url"),
                request.form.get("type"),
                choicedmachines,
                request.form.get("concurrent"),
                request.form.get("looptime"),
                request.form.get("looptimeOptions")
            )
            db.session.add(mission)
            db.session.commit()

            info["missionid"] = mission.id
            fakemachines = mission.fakeMachines
            queenbee = QueenBee(mission.id,fakemachines,config,statusController,request.form,request.files["file"])
            queenbee.start()

        except Exception as e:
            info["result"] = False
            info["errorMsg"] = str(e)
        finally:
            return jsonify(info)
    return render_template("newMission.html",choiced="newMission",timenow=timenow)

@url.route("/stopmission/<int:id>",methods=["POST"])
def stopMission(id):
    try:
        mission = Mission.query.filter_by(id=id).first()
        if mission:
            r = redis.Redis(config.redis_host,config.redis_port,config.redis_db)
            r.set("status-%s" %id,"-1")
    except Exception as e:
        info["result"] = False
        info["errorMsg"] = str(e)
    finally:
        return jsonify(info)


@url.route("/getMissionStatus/<int:id>")
def getMissionStatus(id):
    status = statusController.get(id)
    #print(status)
    # status = {
    #     "looptime":60,
    #     "progress":60,
    #     "initialstate":"初始化redis参数",
    #     "status":"finish",
    #     "elapsed":14,
    #     "samples":1521,
    #     "mintime":0.01,
    #     "maxtime":2.04,
    #     "avgtime":0.5,
    #     "capacity":300,
    #     "errors":18,
    #     "errorpercent":"0.5%"
    # }
    status = json.dumps(status)
    return Response("data:"+status+"\n\n",mimetype="text/event-stream")
