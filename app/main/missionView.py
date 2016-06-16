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
        #return jsonify(info)
        try:
            dictform = dict(request.form)
            apicount = len(dictform.get("apiitems"))
            choicedmachines = dictform.get("choicedMachine")
            print("choicedmachine",choicedmachines)
            urls,types = [],[]
            for i in range(apicount):
                urls.append(dictform.get("url-%s" %(i+1)))
                types.append(dictform.get("type-%s" %(i+1)))
            mission = Mission(
                request.form.get("missionName"),
                urls,
                types,
                choicedmachines,
                request.form.get("concurrent"),
                request.form.get("looptime"),
                request.form.get("looptimeOptions")
            )
            db.session.add(mission)
            db.session.commit()

            info["missionid"] = mission.id
            fakemachines = mission.fakeMachines
            print(request.files)
            queenbee = QueenBee(mission.id,apicount,fakemachines,config,statusController,request.form,request.files)
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
    #print(progress)
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
    sortedElapseList = redis_conn.sort("%s_elapsed" %id)
    length = redis_conn.llen("%s_elapsed" %id)
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


@url.route("/testapi/<apiid>",methods=["GET","POST"])
def testApi(apiid):
    if request.method == "POST":
        form = request.form
        method = form.get("type-%s" %apiid)
        url = form.get("url-%s" %apiid)
        body = form.get("requestbody-%s" %apiid,'{}') or '{}'
        header = form.get("requestheader-%s" %apiid,'{}') or '{}'
        conn_timeout = int(form.get("connectionTimeout-%s" %apiid,5))
        resp_timeout = int(form.get("responseTimeout-%s" %apiid,10))

        r = None
        try:
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
        except Exception as e:
            r = "接口无返回"
        info["message"] = Template(result_template).render(
            url=url,
            method=method,
            req_body=body,
            req_header=header,
            resp_code=r.status_code if not isinstance(r,str) else 2000,
            resp_body=r.text if not isinstance(r,str) else r,
            resp_header=r.headers if not isinstance(r,str) else r
        )

        return jsonify(info)


@url.route("/getapitemplate/<int:id>")
def getApiTemplate(id):
    apilist = Template(apilist_template).render(
        id=id
    )
    return apilist



apilist_template = """
<div class="col-md-11 apilistitem" id="apilistDetail-{{id}}">
    <input type="checkbox" name="apiitems" checked="checked" style="display:none"/>
    <ul class="list-inline">
        <li>Request Type:</li>
        <li>
            <select name="type-{{id}}" class="form-control">
                <option value="GET">GET</option>
                <option value="POST">POST</option>
                <option value="PUT">PUT</option>
                <option value="DELETE">DELETE</option>
            </select>
        </li>
        <li>
            <input id="url-{{id}}" name="url-{{id}}" class="form-control" style="width:800px" maxlength="120" type="text" placeholder="请求地址" value="">
        </li>
        <li><a class="btn btn-default" href="javascript:;" onclick="testapi({{id}})">测试一下</a></li>
        <li><a href="javascript:;" class="btn btn-danger" onclick="delapi({{id}})">删除</a></li>
    </ul>
    <label>Request Settings</label>
    <ul class="nav nav-tabs">
        <li role="presentation" class="active"><a href="#requestbodypanel-{{id}}" aria-controls="requestbodypanel-{{id}}" role="tab" data-toggle="tab">body</a></li>
        <li role="presentation"><a href="#requestheaderpanel-{{id}}" aria-controls="requestheaderpanel-{{id}}" role="tab" data-toggle="tab">header</a></li>
        <li role="presentation"><a href="#requestauthpanel-{{id}}" aria-controls="requestauthpanel-{{id}}" role="tab" data-toggle="tab">authorization</a></li>
    </ul>
    <div class="tab-content">
        <!-- body begin -->
        <div role="tabpanel" class="tab-pane active" id="requestbodypanel-{{id}}">
            <div class="panel-body" id="req-body-panel-{{id}}">
                <ul class="list-inline">
                    <li>上传文件类型：</li>
                    <li>
                        <label class="radio-inline">
                          <input type="radio" name="radio-filetype-{{id}}" value="data" checked="checked" onclick="$('#filefield-{{id}}').hide()"> 请求数据
                        </label>
                    </li>
                    <li>
                        <label class="radio-inline">
                          <input type="radio" name="radio-filetype-{{id}}" value="file" onclick="$('#filefield-{{id}}').show()"> 文件上传
                        </label>
                    </li>
                    <li id="filefield-{{id}}" style="display:none"><input type="text" placeholder="表单field" class="form-control" name="filefield-{{id}}"></li>
                    <li><input type="file" name="file-{{id}}" class="form-control"></li>
                </ul>
                <textarea id="bodyarea-{{id}}" name="requestbody-{{id}}" class="form-control" style="height:100px"></textarea>
            </div>
        </div>
        <!-- body end -->
        <!-- header begin -->
        <div role="tabpanel" class="tab-pane" id="requestheaderpanel-{{id}}">
            <div class="panel-body" id="req-header-panel-{{id}}">
                <textarea id="headerarea" name="requestheader-{{id}}" class="form-control"></textarea>
            </div>
        </div>
        <!-- header ennd -->
        <!-- auth begin -->
        <div role="tabpanel" class="tab-pane" id="requestauthpanel-{{id}}">
            <div class="panel-body" id="req-auth-panel">
                no auth
            </div>
        </div>
        <!-- auth end -->
    </div>
    <label>Assertions</label>
    <ul class="nav nav-tabs">
        <li role="presentation" class="active"><a href="#assertbodypanel-{{id}}" aria-controls="assertbodypanel-{{id}}" role="tab" data-toggle="tab">body</a></li>
        <li role="presentation"><a href="#asserttimepanel-{{id}}" aria-controls="asserttimepanel-{{id}}" role="tab" data-toggle="tab">time</a></li>
        <li role="presentation"><a href="#assertheaderpanel-{{id}}" aria-controls="assertheaderpanel-{{id}}" role="tab" data-toggle="tab">header</a></li>
    </ul>
    <div class="tab-content">
        <div role="tabpanel" class="tab-pane active" id="assertbodypanel-{{id}}">
            <div class="panel-body" id="assert-body-panel-{{id}}">
                <div class="lineitem">
                    equals:<input type="text" name="equalValue-body-{{id}}" style="width:90%">
                </div>
                <div class="lineitem">
                    contains:
                    <label class="checkbox-inline">
                      <input type="checkbox" name="useRegx-body-{{id}}" value="1"> 正则匹配
                    </label>
                    <input type="text" name="containValue-body-{{id}}" style="width:85%">
                </div>
                <div class="lineitem">
                    length:
                    <label class="radio-inline">
                      <input type="radio" name="lengthRadioOptions-body-{{id}}" value="0"> 小于
                    </label>
                    <label class="radio-inline">
                      <input type="radio" name="lengthRadioOptions-body-{{id}}" value="1"> 等于
                    </label>
                    <label class="radio-inline">
                      <input type="radio" name="lengthRadioOptions-body-{{id}}" value="2"> 大于
                    </label>
                    <input type="text" name="lengthValue-body" style="width:10%"> 字节
                </div>
            </div>
        </div>
        <div role="tabpanel" class="tab-pane" id="asserttimepanel-{{id}}">
            <div class="panel-body" id="assert-time-panel-{{id}}">
                <div class="lineitem">
                    connect  timeout: <input type="text" name="connectTimeout-{{id}}" value="5"> 秒
                </div>
                <div class="lineitem">
                    response timeout: <input type="text" name="responseTimeout-{{id}}" value="10"> 秒
                </div>
            </div>
        </div>
        <div role="tabpanel" class="tab-pane" id="assertheaderpanel-{{id}}">
            <div class="panel-body" id="assert-header-panel-{{id}}">
                <div class="lineitem">
                    equals:<input type="text" name="equalValue-header-{{id}}" style="width:90%">
                </div>
                <div class="lineitem">
                    contains:
                    <label class="checkbox-inline">
                      <input type="checkbox" name="useRegx-header-{{id}}" value="1"> 正则匹配
                    </label>
                    <input type="text" name="containValue-header-{{id}}" style="width:85%">
                </div>
                <div class="lineitem">
                    length:
                    <label class="radio-inline">
                      <input type="radio" name="lengthRadioOptions-header-{{id}}" value="0"> 小于
                    </label>
                    <label class="radio-inline">
                      <input type="radio" name="lengthRadioOptions-header-{{id}}" value="1"> 等于
                    </label>
                    <label class="radio-inline">
                      <input type="radio" name="lengthRadioOptions-header-{{id}}" value="2"> 大于
                    </label>
                    <input type="text" name="lengthValue-header-{{id}}" style="width:10%"> 字节
                </div>
            </div>
        </div>
    </div>
    <a href="javascript:;" onclick="addenv({{id}})">添加环境变量</a>
    <div id="envlist-{{id}}" style="padding:20px">
    </div>
</div>
"""



result_template = """
<div style="padding:20px">
    <label>API:</label> {{ url }} [{{ method }}]<br/>
    <label>requestHeader:</label> {{ req_header }} <br/>
    <label>requestBody:</label> {{ req_body }} <br/>
    <hr>
    <label>responseCode:</label> {{ resp_code }} <br/>
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
