# -*- coding: utf-8 -*-
from flask import render_template,request,jsonify
from ..models import db,Mission,info,Machine
from .queenBee import QueenBee,StatusController
from multiprocessing import Manager
from threading import Thread
from jinja2 import Template
from . import url
from config import Config
import json,time,redis,requests


config = Config()
redis_conn = redis.Redis(config.redis_host,config.redis_port,config.redis_db)
statusController = StatusController(redis_conn)


@url.route("/")
@url.route("/missions")
def missions():
    missions = Mission.query.all()
    return render_template("missions.html",choiced="missions",missions=missions[::-1])


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


@url.route("/getErrorChart/<int:id>")
def getErrorChart(id):
    progress = statusController.get(id)
    datas = [
        ("connectionTimeout",progress.get("e_c",0)),
        ("responseTimeout",progress.get("e_r",0)),
        ("unknownError",progress.get("e_u",0)),
        ("assertionError",progress.get("e_a",0))
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
    if length > 0:
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


@url.route("/testapi",methods=["GET","POST"])
def testApi():
    if request.method == "POST":
        form = request.form
        method = form.get("type")
        url = form.get("url")
        body = form.get("requestbody",'{}') or '{}'
        header = form.get("requestheader",'{}') or '{}'
        conn_timeout = int(form.get("connectionTimeout",5))
        resp_timeout = int(form.get("responseTimeout",10))

        r = None

        if method.lower() == "post":
            r = requests.post(url=url,data=eval(body),headers=eval(header),timeout=(conn_timeout,resp_timeout))
        elif method.lower() == "get":
            r = requests.get(url=url,params=eval(body),headers=eval(header),timeout=(conn_timeout,resp_timeout))
        elif method.lower() == "delete":
            r = requests.delete(url=url)
        elif method.lower() == "put":
            r = requests.put(url=url,data=eval(body),headers=eval(header),timeout=(conn_timeout,resp_timeout))
        else:
            info["result"] = False
            info["errorMsg"] = "unsupported method"

        info["message"] = Template(result_template).render(
            url=url,
            method=method,
            req_body=body,
            req_header=header,
            resp_body=r.text,
            resp_header=r.headers
        )

        return jsonify(info)

result_template = """
<div style="padding:20px">
    <label>API:</label> {{ url }} [{{ method }}]<br/>
    <label>requestHeader:</label> {{ req_header }} <br/>
    <label>requestBody:</label> {{ req_body }} <br/>
    <hr>
    <label>responseHeader:</label> <br/>
    <textarea class="form-control" style="height:100px">{{ resp_header }}</textarea>
    <label>responseBody:</label> <br/>
    <textarea class="form-control" style="height:200px">{{ resp_body }}</textarea>
</div>
"""


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
