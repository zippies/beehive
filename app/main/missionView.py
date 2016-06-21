# -*- coding: utf-8 -*-
from flask import render_template,request,jsonify
from ..models import db,Mission,info,Machine
from .queenBee import QueenBee,StatusController
from multiprocessing import Manager
from threading import Thread
from jinja2 import Template
from . import url
from config import Config
from collections import Counter
import json,time,redis,requests,re


config = Config()
redis_conn = redis.Redis(config.redis_host,config.redis_port,config.redis_db)
statusController = StatusController(redis_conn)

test_url = "http://121.43.101.211:8180/suime-user/student/login"
test_data = '{"cellphone":18516042356,"password":"6547436690a26a399603a7096e876a2d"}'

placeholder_data = """
请求body数据,json格式,例：{"username":"abc","password":"abc"}
---- 需要从txt文件读取数据时,使用以下方式：
---- {"username":"{{ file[0] }}","password":"{{ file[1] }}"}
---- 其中{{ file[0] }}将从上传的txt文件第1列读取,{{ file[1] }}会从上传文件的第二列读取,依此类推;txt文件内数据以一个空格隔开，例：username password
""".strip()

placeholder_header = """
请求头,json格式,例: {"content-type":"application/json"}
""".strip()

helponenv = """
【适用场景】<br>
&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp当需要测试多个接口,后一个接口要使用前一个接口的返回值时,需要在前一个接口中配置该项,从响应头或者响应body中将<span style="color:red">正则表达式第一个括号匹配到的值</span>保存为变量,供后续接口使用。<br>
【用法-添加变量】<br>
&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp假设接口body返回内容如下：<br>{"cellphone":"18516042356"}<br>,想要保存手机号,则添加变量,"匹配自"选择"响应体"，正则表达式填写: <span style="color:red">cellphone":"(\d{11})"</span>,变量名填写 <span style="color:red">手机号</span><br>
【用法-使用变量】<br>
&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp在后续接口的请求参数中使用 {{ env(变量名) }} 来获取到全局变量的值。如上例中,使用 <span style="color:red">{{ env(手机号) }}</span> 获取之前接口返回的手机号。
""".strip()

helponfile = """
【适用场景】<br>
&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp当接口需要上传文件,或者请求数据中的字段需要从文件中读取时,需要使用此行配置。<br>
【用法-请求数据】<br>
&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp接口请求数据从文件读取时,上传文件类型选择[请求数据],并上传本地txt文件即可,数据配置参见下面文本框提示。<br>
【用法-文件上传】<br>
&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp接口需要上传文件时,上传文件类型选择[文件上传],并上传本地文件即可；
""".strip()

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
                urls.append(request.form.get("url-%s" %(i+1)))
                types.append(request.form.get("type-%s" %(i+1)))
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

    api_1 = Template(apilist_template).render(
        id=1,
        placeholder_data=placeholder_data,
        placeholder_header=placeholder_header,
        test_url=test_url,
        test_data=test_data,
        helpon=True,
        helponenv=helponenv,
        helponfile=helponfile
    )

    return render_template(
        "newMission.html",
        choiced="newMission",
        api_1=api_1,
        timenow=timenow,
        helponenv=helponenv,
        helponfile=helponfile,
        placeholder_data=placeholder_data,
        placeholder_header=placeholder_header
    )


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
        ("connectTimeout",progress.get("e_c",0)),
        ("responseTimeout",progress.get("e_r",0)),
        ("unknownError",progress.get("e_u",0)),
        ("assertionError",progress.get("e_a",0))
    ]

    datalist = [{"value":data[1],"name":data[0]} for data in datas]

    option = eval(Template(option_template).render(
        title = "错误分布",
        typestr = "['connectTimeout','responseTimeout','unknownError','assertionError']",
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


error_template = """
<ul class="list-group">
    {% for error in errors %}
        <li class="list-group-item">
            <span class="badge">{{ error[1] }}</span>
            {{ error[0] }}
        </li>
    {% endfor %}
</ul>
"""


@url.route("/showerror/<int:id>/<sampletype>")
def showErrorSample(id,sampletype):
    print(id,sampletype)
    redis_errors = redis_conn.lrange("%s_%s" %(id,sampletype),0,-1)
    errors = []
    c = Counter(redis_errors)
    for key in c.keys():
        errors.append((key.decode(),c[key]))

    error_detail = Template(error_template).render(
        errors=errors
    )

    return error_detail


@url.route("/stopmission/<int:id>",methods=["POST"])
def stopMission(id):
    try:
        mission = Mission.query.filter_by(id=id).first()
        if mission:
            redis_conn.set("%s_status" %id,-1)
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
        apicount = len(dict(form).get("apiitems"))
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

        envs = []

        if not isinstance(r,str):
            for i in range(apicount):
                envcount = len(dict(form).get("env-%s" %(i+1),[]))
                for j in range(envcount):
                    envsource = form.get("envsource-%s-%s" %(i+1,j+1))
                    envname = form.get("envname-%s-%s" %(i+1,j+1))
                    envregx = form.get("envregx-%s-%s" %(i+1,j+1))
                    print(envsource,envname,envregx)
                    reg = re.compile(envregx)
                    env = None
                    if envsource == "header":
                        try:
                            env = reg.search(str(r.headers)).groups()[0]
                        except Exception as e:
                            env = str(e)
                    elif envsource == "body":
                        try:
                            env = reg.search(r.text).groups()[0]
                        except Exception as e:
                            env = str(e)
                    envs.append(envname,env)

        info["message"] = Template(result_template).render(
            url=url,
            method=method,
            req_body=body,
            req_header=header,
            resp_code=r.status_code if not isinstance(r,str) else 2000,
            resp_body=r.text if not isinstance(r,str) else r,
            resp_header=r.headers if not isinstance(r,str) else r,
            envs=envs
        )

        return jsonify(info)


@url.route("/getapitemplate/<int:id>")
def getApiTemplate(id):
    apilist = Template(apilist_template).render(
        id=id,
        placeholder_data=placeholder_data,
        placeholder_header=placeholder_header
    )
    return apilist



apilist_template = """
<div class="col-md-11 apilistitem apipanel" id="apilistDetail-{{id}}">
    <h4><span class="label label-success">请求设置</span></h4>
    <div style="padding-left:20px">
        <input type="checkbox" name="apiitems" checked="checked" style="display:none"/>
        <ul class="list-inline" style="width:100%">
            <li>调用方法:</li>
            <li>
                <select name="type-{{id}}" class="form-control">
                    <option value="GET">GET</option>
                    <option value="POST">POST</option>
                    <option value="PUT">PUT</option>
                    <option value="DELETE">DELETE</option>
                </select>
            </li>
            <li style="width:60%">
                <input id="url-{{id}}" name="url-{{id}}" class="form-control" maxlength="120" type="text" placeholder="接口地址" value="{{ test_url }}">
            </li>
            <li><a class="btn btn-default" href="javascript:;" onclick="testapi({{id}})">测试一下</a></li>
            <li><a href="javascript:;" class="btn btn-danger" onclick="delapi({{id}})">删除</a></li>
        </ul>
        
        <ul class="nav nav-tabs">
            <li role="presentation" class="active"><a href="#requestbodypanel-{{id}}" aria-controls="requestbodypanel-{{id}}" role="tab" data-toggle="tab">请求体(body)</a></li>
            <li role="presentation"><a href="#requestheaderpanel-{{id}}" aria-controls="requestheaderpanel-{{id}}" role="tab" data-toggle="tab">请求头(header)</a></li>
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
                        {% if helpon %}
                        <li><a tabindex="0" href="javascript:;" id="helponfile" role="button" data-toggle="popover" data-trigger="focus" title="适用场景及用法" data-content="{{ helponfile }}"><span class="label label-warning">help</span></a></li>
                        {% endif %}
                    </ul>
                    <textarea id="bodyarea-{{id}}" name="requestbody-{{id}}" class="form-control" style="height:100px" placeholder='{{ placeholder_data }}'>{{ test_data }}</textarea>
                </div>
            </div>
            <div role="tabpanel" class="tab-pane" id="requestheaderpanel-{{id}}">
                <div class="panel-body" id="req-header-panel-{{id}}">
                    <textarea id="headerarea" name="requestheader-{{id}}" class="form-control" placeholder='{{ placeholder_header }}'></textarea>
                </div>
            </div>
        </div>
    </div>
    <hr>
    <h4><span class="label label-danger">响应断言</span></h4>
    <div style="padding-left:20px">
        <ul class="nav nav-tabs">
            <li role="presentation" class="active"><a href="#assertbodypanel-{{id}}" aria-controls="assertbodypanel-{{id}}" role="tab" data-toggle="tab">响应体(body)</a></li>
            <li role="presentation"><a href="#asserttimepanel-{{id}}" aria-controls="asserttimepanel-{{id}}" role="tab" data-toggle="tab">连接/响应超时</a></li>
            <li role="presentation"><a href="#assertheaderpanel-{{id}}" aria-controls="assertheaderpanel-{{id}}" role="tab" data-toggle="tab">响应头(header)</a></li>
        </ul>
        <div class="tab-content">
            <div role="tabpanel" class="tab-pane active" id="assertbodypanel-{{id}}">
                <div class="panel-body" id="assert-body-panel-{{id}}">
                    <div class="lineitem">
                        等于: <input type="text" name="equalValue-body-{{id}}" style="width:90%">
                    </div>
                    <div class="lineitem">
                        包含:
                        <label class="checkbox-inline">
                          <input type="checkbox" name="useRegx-body-{{id}}" value="1"> 正则匹配
                        </label>
                        <input type="text" name="containValue-body-{{id}}" style="width:85%">
                    </div>
                    <div class="lineitem">
                        长度:
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
                        连接超时: <input type="text" name="connectTimeout-{{id}}" value="5"> 秒
                    </div>
                    <div class="lineitem">
                        响应超时: <input type="text" name="responseTimeout-{{id}}" value="10"> 秒
                    </div>
                </div>
            </div>
            <div role="tabpanel" class="tab-pane" id="assertheaderpanel-{{id}}">
                <div class="panel-body" id="assert-header-panel-{{id}}">
                    <div class="lineitem">
                        等于: <input type="text" name="equalValue-header-{{id}}" style="width:90%">
                    </div>
                    <div class="lineitem">
                        包含:
                        <label class="checkbox-inline">
                          <input type="checkbox" name="useRegx-header-{{id}}" value="1"> 正则匹配
                        </label>
                        <input type="text" name="containValue-header-{{id}}" style="width:85%">
                    </div>
                    <div class="lineitem">
                        长度:
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
        <hr>
        <a href="javascript:;" onclick="addenv({{id}})">添加变量</a>
        {% if helpon %}
        <a tabindex="0" href="javascript:;" id="helponenv" role="button" data-toggle="popover" data-trigger="focus" title="适用场景及用法" data-content='{{ helponenv }}'><span class="label label-warning">help</span></a>
        {% endif %}
        <div id="envlist-{{id}}" style="padding:20px">
        </div>
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
    <hr>
    <label>保存变量值</label>
    <ul>
    {% for env in envs %}
        <li>{{ env[0] }} = "{{ env[1] }}"</li>
    {% endfor %}
    </ul>
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
