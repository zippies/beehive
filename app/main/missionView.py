# -*- coding: utf-8 -*-
from flask import render_template,request,jsonify
from ..models import db,Mission,info,Machine
from .queenBee import QueenBee,StatusController
from multiprocessing import Manager
from threading import Thread
from jinja2 import Template
from . import url
from config import Config
import json,time,redis


config = Config()
redis_conn = redis.Redis(config.redis_host,config.redis_port,config.redis_db)
statusController = StatusController(redis_conn)

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
            print("queenbee started")
            info["missionid"] = str(mission.id)
        except Exception as e:
            print("Error Occured",e)
            info["result"] = False
            info["errorMsg"] = str(e)
        finally:
            return jsonify(info)
    return render_template("newMission.html",choiced="newMission",timenow=timenow)


@url.route("/freshstatus/<int:id>")
def freshStatus(id):
    progress = statusController.get(id) or {}
    print(progress)
    progress = json.dumps(progress)
    return progress


option_template = """{
    "title" : {
        "text": '{{title}}',
        "x":'center'
    },
    "tooltip" : {
        "trigger": 'item',
        "formatter": "{b} : {c} ({d}%)"
    },
    "legend": {
        "orient" : 'vertical',
        "x" : 'left',
        "data":{{ typestr }}
    },
    "toolbox": {
        "show" : True,
        "feature" : {
            "mark" : {"show": True},
            "dataView" : {"show": True, "readOnly": False},
            "magicType" : {
                "show": True, 
                "type": ['pie', 'funnel'],
                "option": {
                    "funnel": {
                        "x": '25%',
                        "width": '50%',
                        "funnelAlign": 'left'
                    }
                }
            },
            "restore" : {"show": True},
            "saveAsImage" : {"show": True}
        }
    },
    "calculable" : True,
    "series" : [
        {
            "name":'',
            "type":'pie',
            "radius" : '55%',
            "center": ['50%', '60%'],
            "data":{{ datalist }}
        }
    ],
    "color":["#FA8072","#FFAEB9","#FFC125","#FF0000"]
}                  
"""


elapse_template = """
{
    "title": {
        "text": '{{ title }}',
        "x": 'center'
    },
    "tooltip" : {
        "trigger": 'axis',
        "axisPointer" : {
            "type" : 'shadow'
        },
        "formatter": "响应时间 {b}"
    },
    "grid": {
        "left": '3%',
        "right": '4%',
        "bottom": '3%',
        "containLabel": True
    },
    "xAxis": {
        "type" : 'category',
        "splitLine": {"show":False},
        "data" : {{ typelist }}
    },
    "yAxis": {
        "type" : 'value'
    },
    "series": [
        {
            "name": '样本量',
            "type": 'bar',
            "stack": '总量',
            
            "label": {
                "normal": {
                    "show": True,
                    "position": 'inside'
                }
            },
            "data":{{ datalist }}
        }
    ],
    "color":["#7EC0EE"]
}
"""


@url.route("/getErrorChart/<int:id>")
def getErrorChart(id):
    progress = statusController.get(id)
    datas = [
        ("connectionTimeout",progress["e_c"]),
        ("responseTimeout",progress["e_r"]),
        ("unknownError",progress["e_u"]),
        ("assertionError",progress["e_a"])
    ]

    datalist = [{"value":data[1],"name":data[0]} for data in datas]

    option = eval(Template(option_template).render(
        title = "错误分布",
        typestr = "['connectionTimeout','responseTimeout','unknownError','assertionError']",
        datalist = datalist
    ))

    return jsonify(option)


@url.route("/getElapseChart/<int:id>")
def getElapseChart(id):
    p_list = [0.75,0.8,0.85,0.9,0.95,1]
    typelist,datalist = [],[]
    sortedElapseList = redis_conn.sort("%s.elapsed" %id)
    length = redis_conn.llen("%s.elapsed" %id)

    for p in p_list:
        index_count = int(length * p)
        typename = "< %s 秒" %sortedElapseList[index_count-1].decode()[0:4]
        typelist.append(typename)
        datalist.append(index_count)

    option = eval(Template(elapse_template).render(
        title = "响应时间分布",
        typelist = json.dumps(typelist),
        datalist = datalist
    ))

    return jsonify(option)


@url.route("/stopmission/<int:id>",methods=["POST"])
def stopMission(id):
    try:
        mission = Mission.query.filter_by(id=id).first()
        if mission:
            redis_conn.set("status-%s" %id,-1)
    except Exception as e:
        info["result"] = False
        info["errorMsg"] = str(e)
    finally:
        return jsonify(info)