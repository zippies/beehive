from threading import Thread
import pickle,redis,paramiko,platform,os,base64,gnsq,requests,time,json
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
        self.hasLocal = False
        self.config = config
        self.statusController = statusController
        self.form = form
        self.realpath = "%s/%s" %(self.config.UPLOAD_FOLDER,file.filename)
        file.save(self.realpath)
        self.redisclient = None
        self.sshclients = []
        self.readyBee = Queue()
        self.samples = 0
        self.totalelapsed = 0
        self.errors = 0
        self.errorDetails = Queue()
        self.analysisBees = []
        self.starttime = None
        self.min_elapsed = 10
        self.max_elapsed = 0
        self.looptime = 0
        self.end = False

    def dispatchClient(self,machine):
        if machine.ip == self.config.localip:
            self.hasLocal = True
            return
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

        sftp.put(self.config.client_path,"clienthive")

        t.close()

        stdin,stdout,stderr = ssh.exec_command("chmod a+x clienthive")
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

        data = self.form.get("requestbody") or {}
        header = self.form.get("requestheader") or {}
        startDelay = self.form.get("startDelay")
        connectTimeout = self.form.get("connectTimeout")
        responseTimeout = self.form.get("responseTimeout")
        concurrent = int(self.form.get("concurrent"))
        beecount = self.form.get("beecount")

        url = self.form.get("url")
        method = self.form.get("type")

        if self.form.get("looptimeOptions") == "0":
            self.looptime = int(self.form.get("looptime"))
        elif self.form.get("looptimeOptions") == "1":
            self.looptime = int(self.form.get("looptime")) * 60
        else:
            self.looptime = int(self.form.get("looptime")) * 3600


        if not beecount and int(concurrent/2) > 500:
            beecount = 500
        else:
            beecount = int(concurrent/2)

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
        self.redisclient.set("looptime", self.looptime)
        self.redisclient.set("method", method)
        conc_avg,conc_left = int(concurrent / len(self.machines)),concurrent%len(self.machines)
        for index,machine in enumerate(self.machines):
            if index == 0:
                self.redisclient.hset(machine.ip,"concurrent",conc_avg+conc_left)
            else:
                self.redisclient.hset(machine.ip,"concurrent",conc_avg)
            self.redisclient.hset(machine.ip,"header",header)
            self.redisclient.hset(machine.ip,"data",data)

        if "{{file[" in data and self.form.get("checkbox-file"):
            with open(self.realpath,encoding="utf-8") as f:
                lines = [line.strip() for line in f.readlines() if line.strip()]
                for line in lines:
                    self.redisclient.lpush("filedata",line)

                self.redisclient.set("dataCount",len(lines))
        elif self.form.get("checkbox-file"):
            with open(self.realpath,"rb") as f:
                self.redisclient.lpush("file",f.read())
        else:
            pass

        return
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
        self.statusController.set(self.id, {"progress": 4, "initialstate": "启动压测客户端"})

        maleBees = []
        for sshclient in self.sshclients:
            bee = Thread(target=self.hitHoney,args=(sshclient,))
            bee.setDaemon(True)
            maleBees.append(bee)

        for bee in maleBees:
            bee.start()

        localBee = None
        if self.hasLocal:
            localBee = Thread(target=self.hitHoney)
            localBee.setDaemon(True)
            localBee.start()

        femaleBees = []
        for i in range(beecount):
            goodBee = Thread(target=self.collectGoodHoney,args=(i,))
            goodBee.setDaemon(True)
            badBee = Thread(target=self.collectBadHoney,args=(i,))
            badBee.setDaemon(True)
            femaleBees.append(goodBee)
            femaleBees.append(badBee)
        
        for bee in femaleBees:
            bee.start()

        if self.clientReady():
            self.redisclient.set("status",1)
            self.starttime = time.time()
            self.statusController.set(self.id, {"looptime":self.looptime,"progress": 1, "status":"running","initialstate": "开始压测"})
        else:
            assert 1==2,"start client failed"

        print("mission real started")

        time.sleep(1)
        backend = Thread(target=self.dumpStatus)
        backend.setDaemon(True)
        backend.start()

        for bee in maleBees:
            bee.join()

        if self.hasLocal:
            localBee.join()

        print("Mission finished and bees on the way home")
        self.statusController.set(self.id, {"looptime":self.looptime,"progress": self.looptime, "status":"running","initialstate": "开始压测"})

        while True:
            if self.honeyCount and self.honeyCount == self.samples:
                self.end = True
                break
            else:
                time.sleep(2)

        self.clear()

        print("All bees returned",self.samples)

    def clear(self):
        for bee in self.analysisBees:
            bee.close()

        self.redisclient.flushdb()

        r = requests.delete("http://%s:4171/api/topics/failed" %self.config.nsq_host)
        r = requests.delete("http://%s:4171/api/topics/success" %self.config.nsq_host)
        print("topic deleted")

    def clientReady(self):
        ready = True
        for client in self.sshclients:
            start = time.time()
            while time.time()-start < 10:
                stdin,stdout,stderr = client.exec_command("pgrep -lf clienthive")
                info = stdout.read().decode()
                if "clienthive" in info:
                    break
                else:
                    print("not ready",info)
            else:
                ready = False
                break

        return ready

    def hitHoney(self,sshClient=None):
        cmd = "./clienthive %s:4150 %s:%s" %(self.config.nsq_host,self.config.redis_host,self.config.redis_port)
        if not sshClient:
            stdout = os.popen(cmd)
            self.readyBee.put(1)
            print("local ready")
            output = stdout.read()
        else:
            stdin,stdout,stderr = sshClient.exec_command(cmd)
            self.readyBee.put(1)
            output = stdout.read()

    def collectGoodHoney(self,honeyid):
        """
        type Report struct {
            Url           string
            Method        string
            Elapsed       float64
            Machine_ip    string
            Goroutine_id  int
            ErrorMsg      string
            StatusCode    int
            Body          string
            ContentLength int
            Header        http.Header
            Cookies       []*http.Cookie
        }
        """
        bee = gnsq.Reader("success","goodBee","%s:4150" %self.config.nsq_host)
        self.analysisBees.append(bee)

        @bee.on_message.connect
        def handler(bee, message):
            self.samples += 1
            m = json.loads(message.body.decode())
            self.totalelapsed += m["Elapsed"]

            if not self.min_elapsed or m["Elapsed"] < self.min_elapsed:
                self.min_elapsed = m["Elapsed"]


            if not self.max_elapsed or m["Elapsed"] > self.max_elapsed:
                self.max_elapsed = m["Elapsed"]

            if m["ErrorMsg"]:
                self.errors += 1

        bee.start()


    def collectBadHoney(self,honeyid):
        bee = gnsq.Reader("failed","badBee","%s:4150" %self.config.nsq_host)
        self.analysisBees.append(bee)
        @bee.on_message.connect
        def handler(bee, message):
            self.samples += 1
            m = message.body.decode()
            self.errors += 1
            self.errorDetails.put(m)

        bee.start()


    @property
    def honeyCount(self):
        url = "http://%s:4171/api/nodes/nsp:4151" %self.config.nsq_host
        message_count = requests.get(url).json()["total_messages"]
        return message_count

    @property
    def progress(self):
        elapsed = time.time() - self.starttime
        try:
            avg_elapsed = self.totalelapsed / (self.samples - self.errors)
            error_percent = round(self.errors / self.samples,4) * 100
        except ZeroDivisionError:
            avg_elapsed = 0
            error_percent = 0

        throught = (self.samples-self.errors) / (elapsed if elapsed < self.looptime else self.looptime)

        return {
        "progress":int(elapsed) if elapsed < self.looptime else self.looptime,
        "elapsed":int(elapsed) if elapsed < self.looptime else self.looptime,
        "status":"finish" if self.end else "running",
        "looptime":self.looptime,
        "samples":self.samples,
        "min_elapsed":round(self.min_elapsed,3),
        "max_elapsed":round(self.max_elapsed,3),
        "avg_elapsed":round(avg_elapsed,3),
        "throught":round(throught,2),
        "errors":self.errors,
        "error_percent":round(error_percent,2)
        }

    def dumpStatus(self):
        while not self.end:
            self.statusController.set(self.id,self.progress)
            time.sleep(1)
        else:
            self.statusController.set(self.id,self.progress)













