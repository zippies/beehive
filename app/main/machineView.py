# -*- coding: utf-8 -*-
from flask import render_template,request,jsonify,Response
from ..models import db,Mission,Machine,info
from jinja2 import Template
from . import url
import json,paramiko

@url.route("/machines")
def machines():
    machines = Machine.query.all()
    return render_template("machines.html",choiced="machines",machines=machines)

machine_template = """
{% for machine in machines %}
    {% if source == 0 %}
        <label class="col-lg-3 col-md-4 col-sm-2" style="margin-bottom:10px">
        <input type="checkbox" name="choicedMachine" value="{{ machine.id }}" onclick="showChange({{machine.id}})" />
    {% else %}
        <div class="col-lg-3 col-md-4 col-sm-2" id="machinediv_{{ machine.id }}" style="margin-bottom:10px">
    {% endif %}
            <div class="machine" id="machinediv_{{ machine.id }}" style="border:1px solid #D9D9D9;border-radius:5px;padding:15px;{% if source == 1%}background-color:#87CEFF;{% endif %}font-family:'楷体';">
                <div style="text-align:center;margin-bottom:15px">
                    {% if machine.system == 'windows' %}
                        <img src="static/imgs/windows.png" alt="machine">
                    {% elif machine.system == 'linux' %}
                        <img src="static/imgs/linux.png" alt="machine">
                    {% elif machine.system == 'mac' %}
                        <img src="static/imgs/mac.png" alt="machine">
                    {% else %}
                        <img src="static/imgs/machine.png" alt="machine">
                    {% endif %}
                </div>

                <table class="table table-bordered table-striped" id="machineinfotable">
                    <tbody>
                        <tr>
                            <th>机器名称:</th>
                            <td>
                            {% if source == 0 %}
                                {{ machine.name }}
                            {% else %}
                                <input class="machineinfo_{{ machine.id }}" name="name" type="text" value="{{ machine.name }}" disabled="disabled">
                            {% endif %}
                            </td>
                        </tr>
                        <tr>
                            <th>机器IP:</th>
                            <td>
                            {% if source == 0 %}
                                {{ machine.ip }}
                            {% else %}
                                <input class="machineinfo_{{ machine.id }}" name="ip" type="text" value="{{ machine.ip }}" disabled="disabled">
                            {% endif %}
                            </td>
                        </tr>
                        <tr>
                            <th>系统核数:</th>
                            <td>
                            {% if source == 0 %}
                                {{ machine.cpu }}
                            {% else %}
                                <input class="machineinfo_{{ machine.id }}" name="cpu" type="text" value="{{ machine.cpu }}" disabled="disabled">
                            {% endif %}
                            </td>
                        </tr>
                        <tr>
                            <th>内存大小:</th>
                            <td>
                            {% if source == 0 %}
                                {{ machine.memory }}
                            {% else %}
                                <input class="machineinfo_{{ machine.id }}" name="memory" type="text" value="{{ machine.memory }}" disabled="disabled">
                            {% endif %}
                            </td>
                        </tr>
                        <tr>
                            <th>磁盘大小:</th>
                            <td>
                            {% if source == 0 %}
                                {{ machine.disk }}
                            {% else %}
                                <input class="machineinfo_{{ machine.id }}" name="disk" type="text" value="{{ machine.disk }}" disabled="disabled">
                            {% endif %}
                            </td>
                        </tr>
                    </tbody>
                </table>
    {% if source == 0 %}
            </div>
        </label>
    {% else %}
                    <a href="javascript:;" class="btn btn-info" id="editmachine_{{ machine.id }}" onclick="editmachine({{ machine.id }})">编辑</a>
                    <a href="javascript:;" class="btn btn-info" id="saveedit_{{ machine.id }}" onclick="saveedit({{ machine.id }})" style="display:none">保存</a>
                    <a href="javascript:;" class="btn btn-warning" id="delmachine_{{ machine.id }}" onclick="delmachine({{ machine.id }})">删除</a>
            </div>
        </div>
    {% endif %}
{% endfor %}
"""

@url.route("/getmachines")
def getMachines():
    machines = Machine.query.all()
    source = int(request.args.get("source"))
    data = Template(machine_template).render(
        machines=machines,
        source=source
    )
    return data

@url.route("/newmachine",methods=["POST"])
def newMachine():
    rsa = request.files["file"]
    rsacontent = rsa.stream.read().decode()
    ip = request.form.get("ip").strip()
    system = request.form.get("system")
    user = request.form.get("user")
    password = request.form.get("password")
    sshtype = request.form.get("sshtype")
    port = int(request.form.get("port")) or 22

    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        if sshtype == "password":
            ssh.connect(hostname=ip,port=port,username=user,password=password)
        elif sshtype == "publickey":
            ssh.connect(hostname=ip,port=port,username=user,pkey=rsacontent)
        else:
            info["result"] = False
            info["errorMsg"] = "unsupport sshtype"
            return jsonify(info)
        
        stdin,stdout,stderr = ssh.exec_command("whoami")
        if user != stdout.readline().strip():
            info["result"] = False
            info["errorMsg"] = stderr.read().decode()
            return jsonify(info)


        cmd_disk = "df -m"
        stdin,stdout,stderr = ssh.exec_command(cmd_disk)

        disk = [i.strip() for i in stdout.readlines()[1].split(" ") if i.strip()][1]

        cmd_mem = "free -m"
        stdin,stdout,stderr = ssh.exec_command(cmd_mem)
        m = [i.strip() for i in stdout.readlines()[1].split(" ") if i.strip()][1]

        ssh.close()

        machine = Machine(
            request.form.get("name"),
            ip=ip,
            system=system,
            sshtype=sshtype,
            user=user,
            port=port,
            password=password,
            rsa=rsacontent,
            memory="%sM" %m,
            cpu=1,
            disk="%sM" %disk
        )
        db.session.add(machine)
        db.session.commit()
    except Exception as e:
        info["result"] = False
        info["errorMsg"] = str(e)
    finally:
        return jsonify(info)

@url.route("/editmachine")
def editMachine():
    req = request.args
    id = int(req.get("id"))
    try:
        machine = Machine.query.filter_by(id=id).first()
        if machine:
            machine.name = req.get("name")
            machine.ip = req.get("ip")
            machine.cpu = req.get("cpu")
            machine.memory = req.get("memory")
            machine.disk = req.get("disk")
            db.session.add(machine)
            db.session.commit()
    except Exception as e:
        info["result"] = False
        info["errorMsg"] = str(e)
    finally:
        return jsonify(info)

@url.route("/delmachine/<int:id>")
def delMachine(id):
    try:
        machine = Machine.query.filter_by(id=id).first()
        if machine:
            db.session.delete(machine)
            db.session.commit()
    except Exception as e:
        info["result"] = False
        info["errorMsg"] = str(e)
    finally:
        return jsonify(info)