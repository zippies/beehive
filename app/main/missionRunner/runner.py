from threading import Thread
import pickle,redis,paramiko,platform,os

class StatusController(object):

    def __init__(self,filename):
        data = {}
        self.filename = filename
        pickle.dump(data,open("%s.pkl" %filename,"wb"))

    def get(self,key):
        data = pickle.load(open("%s.pkl" %self.filename,"rb"))
        if key in data.keys():
            return data[key]
        else:
            return None

    def set(self,key,value):
        data = pickle.load(open("%s.pkl" %self.filename,"rb"))
        data[key] = value
        pickle.dump(data, open("%s.pkl" %self.filename, "wb"))
        return True

class MissionRunner(Thread):
    def __init__(self,id,machines,config,statusController,form,file):
        Thread.__init__(self)
        self.id = id
        self.machines = machines
        self.config = config
        self.statusController = statusController
        self.form = form
        self.file = file

    def run(self):
        """
        ('url', 'http://121.43.101.211:8180/suime-user/student/login'),     # url
        ('type', 'POST'),                                                   # 请求类型
        ('requestbody', '{"cellphone":18516042356,"password":"6547436690a26a399603a7096e876a2d"}'),  #请求参数body
        ('requestheader', '{"hello":"chris"}'),                             # 请求header
        ('concurrent', '10'),                                               # 并发量
        ('looptime', '120'),                                                # 循环时间
        ('startDelay', ''),                                                 # 启动延迟
        ('looptimeOptions', '0'),                                           # 延迟类型：秒，分，时
        ('choicedMachine', '1'),                                            # 已选择的机器数
        ('missionName', 'Mission_2016-05-18 16:03:26'),                     # 任务名称
        ('checkbox-file', '1'),                                             # 请求body包含file
        ('checkbox-data', '1'),                                             # 请求body包含data

        ('lengthValue-body', '250'),                                        # assert 返回body的长度（字节）
        ('equalValue-header', ''),                                          # assert 返回header是否等于该值
        ('responseTimeout', '10'),                                          # assert 响应超时（秒）
        ('lengthValue-header', ''),                                         # assert 返回header的长度（字节）
        ('containValue-body', ''),                                          # assert 返回body是否包含该值
        ('connectTimeout', '5'),                                            # assert 连接超时（秒）
        ('equalValue-body', '{"result":1}'),                                # assert 返回body是否等于该值
        ('containValue-header', ''),                                        # assert 返回header是否包含该值
        ('lengthRadioOptions-body', '0')                                    # assert 返回body长度比较类型（大于/等于/小于）
        ('lengthRadioOptions-header', '0')                                  # assert 返回header长度比较类型（大于/等于/小于）
        """
        ############################################解析mission配置######################################################
        self.statusController.set(self.id,{"progress":1,"initialstate":"解析mission配置"})
        looptime = None
        data = None
        file = None
        header = self.form.get("requestheader")
        startDelay = self.form.get("startDelay")
        connectTimeout = self.form.get("connectTimeout")
        responseTimeout = self.form.get("responseTimeout")
        url = self.form.get("url")
        method = self.form.get("type")

        if self.form.get("looptimeOptions") == "0":
            looptime = int(self.form.get("looptime"))
        elif self.form.get("looptimeOptions") == "1":
            looptime = int(self.form.get("looptime")) * 60
        else:
            looptime = int(self.form.get("looptime")) * 3600

        if self.form.get("checkbox-data") and self.form.get("checkbox-file"):
            data = self.form.get("requestbody")  #如果data中有{{ file-name }} 则从file中读取name字段代替
            file = self.file
        elif self.form.get("checkbox-data"):
            data = self.form.get("requestbody")
        elif self.form.get("checkbox-file"):
            data = {}
        else:
            data = {}

        ####  check options
        bodylengthtype = self.form.get("lengthRadioOptions-body")
        bodylength = self.form.get("lengthValue-body")
        headerlengthtype = self.form.get("lengthRadioOptions-header")
        headerlength = self.form.get("lengthValue-header")
        bodyequal = self.form.get("equalValue-body")
        headerequal = self.form.get("equalValue-header")
        bodyusereg = self.form.get("useRegx-body")
        headerusereg = self.form.get("useRegx-header")
        bodyContainValue = self.form.get("containValue-body")
        headerContainValue = self.form.get("containValue-header")
        ############################################初始化redis######################################################
        self.statusController.set(self.id, {"progress": 2, "initialstate": "初始化redis参数"})
        r = redis.Redis(host=self.config.redis_host,port=self.config.redis_port,db=self.config.redis_db)
        r.set("url",url)
        r.set("responseTimeout", responseTimeout)
        r.set("connectTimeout", connectTimeout)
        r.set("startDelay", startDelay)
        r.set("looptime", looptime)
        r.set("method", method)
        for machine in self.machines:
            r.hset(machine.ip,"concurrent",10)
            r.hset(machine.ip,"header",header)
            r.hset(machine.ip,"data",{})
            r.hset(machine.ip,"status",0)
        ##############################################链接远程机器####################################################
        self.statusController.set(self.id, {"progress": 3, "initialstate": "连接远程机器/下发客户端程序"})
        sshClients = []
        for machine in self.machines:
            ssh = paramiko.SSHClient()
            ssh.load_system_host_keys()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            if machine.sshtype == "password":
                if platform.system().lower() == "windows":  #widows 密码
                    cmd = "pscp {user}@{ip} -pw {password} -b {file}".format(user=machine.user,ip=machine.ip,password=machine.password,file="")
                else:   #linux 密码
                    cmd = "scp {file} {user}:{password}@{ip}:{path}".format(user=machine.user,ip=machine.ip,password=machine.password,file="",path="")
                result = os.popen(cmd)
                print(result.read())
                ssh.connect(machine.ip, port=machine.port, username=machine.user, password=machine.password)
            else:
                if platform.system().lower() == "windows":  #windows 密钥
                    cmd = "pscp {user}@{ip} -i {pkey} ".format(user=machine.user,ip=machine.ip,pkey=machine.rsa)
                else:   #linux 密钥
                    cmd = "scp {file} {user}@{ip}:{path}".format(user=machine.user,ip=machine.ip,pkey=machine.rsa,file="",path="")
                result = os.popen(cmd)
                print(result.read())
                ssh.connect(machine.ip, port=machine.port, username=machine.user, pkey=machine.rsa)

            sshClients.append(ssh)
        ##############################################启动压测客户端####################################################
