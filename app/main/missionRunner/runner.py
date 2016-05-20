from threading import Thread
import pickle,redis,paramiko,platform,os,base64,gnsq,requests,time
from multiprocessing import Manager,Queue

system = platform.system().lower()

class StatusController(object):

    def __init__(self):
        if system == "windows":
            data = {}
            self.filename = "statusController"
            pickle.dump(data,open("%s.pkl" %filename,"wb"))
        else:
            self.data = Manager().dict()

    def get(self,key):
        if system == "windows":
            data = pickle.load(open("%s.pkl" %self.filename,"rb"))
            if key in data.keys():
                return data[key]
            else:
                return None
        else:
            return self.data.get(key,None)

    def set(self,key,value):
        if system == "windows":
            data = pickle.load(open("%s.pkl" %self.filename,"rb"))
            data[key] = value
            pickle.dump(data, open("%s.pkl" %self.filename, "wb"))
            return True
        else:
            self.data[key] = value
            return True


class QueenBee(Thread):
    def __init__(self,id,machines,config,statusController,form,file):
        Thread.__init__(self)
        self.id = id
        self.machines = machines
        self.config = config
        self.statusController = statusController
        self.form = form
        self.file = file
        self.redisclient = None
        self.sshclients = []
        self.progress = None
        self.honeyCount = None
        self.honeyBottle = Queue()
        self.readyBee = Queue()
        self.successBees = []
        self.errorBees = []


    def dispatchClient(self,machine):
        ssh = paramiko.SSHClient()
        ssh.load_system_host_keys()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        t = paramiko.Transport((machine.ip,machine.port))
        if machine.sshtype == "password":
            ssh.connect(machine.ip, port=machine.port, username=machine.user, password=machine.password)
            t.connect(username=machine.user,password=machine.password)
        else:
            key = paramiko.RSAKey(data=base64.decodestring(machine.rsa))
            ssh.get_host_keys().add(machine.name, 'ssh-rsa', key)
            ssh.connect(machine.name, port=machine.port, username=machine.user)
            t.connect(machine.name, port=machine.port, username=machine.user)

        sftp = paramiko.SFTPClient.from_transport(t)

        sftp.put(self.config.client_path,"client")

        t.close()

        stdin,stdout,stderr = ssh.exec_command("chmod a+x client")
        self.sshclients.append(ssh)
        print("finish",machine.name)


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
        header = self.form.get("requestheader") or {}
        startDelay = self.form.get("startDelay")
        connectTimeout = self.form.get("connectTimeout")
        responseTimeout = self.form.get("responseTimeout")
        concurrent = int(self.form.get("concurrent"))
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
        self.redisclient = redis.Redis(host=self.config.redis_host,port=self.config.redis_port,db=self.config.redis_db)
        self.redisclient.set("url",url)
        self.redisclient.set("responseTimeout", responseTimeout)
        self.redisclient.set("connectTimeout", connectTimeout)
        self.redisclient.set("startDelay", startDelay)
        self.redisclient.set("looptime", looptime)
        self.redisclient.set("method", method)
        conc_avg,conc_left = int(concurrent / len(self.machines)),concurrent%len(self.machines)
        for index,machine in enumerate(self.machines):
            if index == 0:
                self.redisclient.hset(machine.ip,"concurrent",conc_avg+conc_left)
            else:
                self.redisclient.hset(machine.ip,"concurrent",conc_avg)
            self.redisclient.hset(machine.ip,"header",header)
            self.redisclient.hset(machine.ip,"data",data)
            #self.redisclient.hset(machine.ip,"status",0)
        ##############################################连接远程机器####################################################
        self.statusController.set(self.id, {"progress": 3, "initialstate": "连接远程机器/下发压测程序"})

        dispatchers = []
        for machine in self.machines:
            dispatcher = Thread(target=self.dispatchClient,args=(machine,))
            dispatcher.setDaemon(True)
            dispatchers.append(dispatcher)

        for dispatcher in dispatchers:
            dispatcher.start()

        for dispatcher in dispatchers:
            dispatcher.join()

        #############################################启动压测客户端并收集压测数据####################################################
        self.statusController.set(self.id, {"progress": 4, "initialstate": "启动压测客户端并收集压测数据"})

        maleBees = []
        for sshclient in self.sshclients:
            bee = Thread(target=self.hitHoney,args=(sshclient,))
            bee.setDaemon(True)
            maleBees.append(bee)

        for bee in maleBees:
            bee.start()

        femaleBees = []
        for i in range(5):
            femaleBee = Thread(target=self.collectHoney,args=(i,))
            femaleBee.setDaemon(True)
            femaleBees.append(femaleBee)
        
        for bee in femaleBees:
            bee.start()

        while True:
            if self.readBee.qsize == len(self.machines):
                self.redisclient.set("status",1)
                break

        print("mission real started")

        for bee in maleBees:
            bee.join()
        print("Mission finished and bees on the way home")


        self.honeyCount = self.countHoney()


        while True:
            if self.honeyCount and self.honeyCount == self.honeyBottle.qsize():
                break
            else:
                time.sleep(2)
                print(self.honeyCount,self.honeyBottle.qsize())

        print("All bees returned")


    def hitHoney(self,sshClient):
        stdin,stdout,stderr = sshClient.exec_command("./client %s %s" %(self.config.nsq_addr,self.config.redis_addr))
        self.readyBee.put(1)
        output = stdout.read()

    def collectHoney(self,honeyid):
        bee = gnsq.Reader("success","successBee",self.config.nsq_addr)

        @bee.on_message.connect
        def handler(bee, message):
            self.honeyBottle.put(1)

        bee.start()

    def countHoney(self):
        url = "http://104.236.5.165:4171/api/nodes/nsp:4151"
        message_count = requests.get(url).json()["total_messages"]
        return message_count

    def dumpStatus(self):
        self.statusController.set(self.id,self.progress)














