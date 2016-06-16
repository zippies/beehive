from threading import Thread
import pickle,redis,paramiko,platform,os,base64,gnsq,requests,time,json,re
from multiprocessing import Manager,Queue
from collections import namedtuple

system = platform.system().lower()

class StatusController(object):

    def __init__(self,redis_conn):
        self.redis_conn = redis_conn

    def get(self,key):
        data = self.redis_conn.hget("progress",key).decode()
        return eval(data)

    def set(self,key,value):
        self.redis_conn.hset("progress",key,value)
        return True

class QueenBee(Thread):
    def __init__(self,id,apicount,machines,config,statusController,form,files):
        Thread.__init__(self)
        self.id = id
        self.apicount = apicount
        self.machines = machines
        self.hasLocal = False
        self.config = config
        self.statusController = statusController
        self.form = form
        self.checkobjs = self._initCheckObjs(apicount)
        self.files = []
        for file in files.values():
            if file.filename:
                datafile = "%s/%s" %(self.config.UPLOAD_FOLDER,file.filename)
                file.save(datafile)
                self.files.append((file.filename,datafile))
            else:
                self.files.append(None)
        self.redisclient = None
        self.sshclients = []
        self.samples = 0
        self.totalelapsed = 0
        self.errors = 0
        self.successSample = None
        self.errorSample = None
        self.analysisBees = []
        self.starttime = None
        self.min_elapsed = 0
        self.max_elapsed = 0
        self.looptime = 0
        self.end = False

        self.connectionTimeouts = 0
        self.responseTimeouts = 0
        self.unknownErrors = 0
        self.assertionErrors = 0

    def _initCheckObjs(self,apicount):
        checkobjs = []
        checkobj = namedtuple("checkobj","bodyequal headerequal bodycontains headercontains bodyusereg headerusereg bodylengthtype bodylength headerlengthtype headerlength")
        for i in range(apicount):
            checkobjs.append(checkobj(
                self.form.get("equalValue-body-%s" %(i+1)),
                self.form.get("equalValue-header-%s" %(i+1)),
                self.form.get("containValue-body-%s" %(i+1)),
                self.form.get("containValue-header-%s" %(i+1)),
                self.form.get("useRegx-body-%s" %(i+1)),
                self.form.get("useRegx-header-%s" %(i+1)),
                self.form.get("lengthRadioOptions-body-%s" %(i+1)),
                int(self.form.get("lengthValue-body-%s" %(i+1))) if self.form.get("lengthValue-body-%s" %(i+1)) else None,
                self.form.get("lengthRadioOptions-header-%s" %(i+1)),
                int(self.form.get("lengthValue-header-%s" %(i+1))) if self.form.get("lengthValue-header-%s" %(i+1)) else None
            ))
        return checkobjs

    def dispatchClient(self,machine):
        if machine.ip == self.config.localip:
            self.hasLocal = True
            print("dispatch local ok")
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
        ############################################解析mission配置######################################################
        self.statusController.set(self.id,{"p":1,"i":"解析mission配置","s":0})

        startDelay = self.form.get("startDelay")
        concurrent = int(self.form.get("concurrent"))
        beecount = self.form.get("beecount")

        if self.form.get("looptimeOptions") == "0":
            self.looptime = int(self.form.get("looptime"))
        elif self.form.get("looptimeOptions") == "1":
            self.looptime = int(self.form.get("looptime")) * 60
        else:
            self.looptime = int(self.form.get("looptime")) * 3600

        if not beecount and int(concurrent/2) > 500:
            beecount = 500
        else:
            beecount = int(concurrent/2) or 1

        ############################################初始化redis######################################################
        self.statusController.set(self.id, {"p": 2, "i": "初始化redis参数","s":0})

        self.redisclient = redis.Redis(host=self.config.redis_host,port=self.config.redis_port,db=self.config.redis_db)
        conc_avg,conc_left = int(concurrent / len(self.machines)),concurrent%len(self.machines)
        for index,machine in enumerate(self.machines):
            key = "%s_%s" %(self.id,machine.ip)
            self.redisclient.hset(key,"ready",0)

            if index == 0:
                self.redisclient.hset(key,"concurrent",conc_avg+conc_left)
            else:
                self.redisclient.hset(key,"concurrent",conc_avg)

        self.redisclient.mset({"%s_startdelay" %self.id:startDelay,"%s_looptime" %self.id:self.looptime,"%s_status" %self.id:0})
        for i in range(self.apicount):
            data = self.form.get("requestbody-%s" %(i+1))
            self.redisclient.rpush("%s_urls" %self.id,self.form.get("url-%s" %(i+1)))
            self.redisclient.rpush("%s_methods" %self.id,self.form.get("type-%s" %(i+1)))
            self.redisclient.rpush("%s_resptimeouts" %self.id,self.form.get("responseTimeout-%s" %(i+1)))
            self.redisclient.rpush("%s_conntimeouts" %self.id,self.form.get("connectTimeout-%s" %(i+1)))
            self.redisclient.rpush("%s_headers" %self.id,self.form.get("requestheader-%s" %(i+1)) or "{}")
            self.redisclient.rpush("%s_datas" %self.id,data or "{}")

            radiofile = self.form.get("radio-filetype-%s" %(i+1))

            m = re.search(r"{{ *file\[\d+\] *}}",data)

            if radiofile == "data" and m and self.files[i]:
                with open(self.files[i][1],encoding="utf-8") as f:
                    lines = [line.strip() for line in f.readlines() if line.strip()]
                    for line in lines:
                        self.redisclient.rpush("%s_filedata_%s" %(self.id,i),line)

                    self.redisclient.set("%s_datacount_%s" %(self.id,i),len(lines))
                    self.redisclient.rpush("%s_filetypes" %self.id,2)
            elif radiofile == "file" and self.files[i]:
                with open(self.files[i][1],"rb") as f:
                    self.redisclient.hmset("%s_file_%s" %(self.id,i),{"filecontent":f.read(),"filename":self.files[i][0],"filefield":self.form.get("filefield-%s" %(i+1))})
                    self.redisclient.rpush("%s_filetypes" %self.id,1)
            else:
                self.redisclient.rpush("%s_filetypes" %self.id,0)

            envcount = len(dict(self.form).get("env-%s" %(i+1),[]))
            self.redisclient.rpush("%s_envcounts" %self.id,envcount)
            for j in range(envcount):
                envsource = self.form.get("envsource-%s-%s" %(i+1,j+1))
                envname = self.form.get("envname-%s-%s" %(i+1,j+1))
                envregx = self.form.get("envregx-%s-%s" %(i+1,j+1))
                self.redisclient.hmset("%s_env_%s_%s" %(self.id,i,j),{"source":envsource,"name":envname,"regx":envregx})

        ##############################################连接远程机器####################################################
        self.statusController.set(self.id, {"p": 3, "i": "连接远程机器/下发压测程序","s":0})

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
        self.statusController.set(self.id, {"p": 4, "i": "启动压测客户端","s":0})

        maleBees = []
        for sshclient in self.sshclients:
            bee = Thread(target=self.hitHoney,args=(sshclient,))
            maleBees.append(bee)

        for bee in maleBees:
            bee.start()


        localBee = None
        if self.hasLocal:
            localBee = Thread(target=self.hitHoney)
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
            print("client ready")
            self.redisclient.set("%s_status" %self.id,1)
            self.starttime = time.time()
            self.statusController.set(self.id, {"l":self.looptime,"p": 1, "s":1,"i": "开始压测"})
        else:
            #assert 1==2,"start client failed"
            self.statusController.set(self.id,{"s":-1,"i":"client not ready after 10 seconds"})
            return

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
        self.statusController.set(self.id, {"l":self.looptime,"p": self.looptime, "s":1,"i": "开始压测"})

        while True:
            if self.honeyCount and self.honeyCount == self.samples:
                self.end = True
                break
            else:
                print(self.honeyCount,"not equals",self.samples)
                time.sleep(2)

        self.clear()

        print("All bees returned,got",self.samples,"messages")

    def clear(self):
        for bee in self.analysisBees:
            bee.close()

    def clientReady(self):
        ready = True
        count = 0
        total = len(self.machines)
        start = time.time()

        while time.time()-start < 10:
            for machine in self.machines:
                key = "%s_%s" %(self.id,machine.ip)
                status = self.redisclient.hget(key,"ready")
                if status and int(status) == 1:
                    count += 1

            if count == total:
                break
            else:
                count = 0
        else:
            ready = False

        return ready

    def hitHoney(self,sshClient=None):
        cmd = "./clienthive %s:4150 %s:%s %s" %(self.config.nsq_host,self.config.redis_host,self.config.redis_port,self.id)
        if not sshClient:
            stdout = os.popen(cmd)
            print("local clienthive startted")
            output = stdout.read()
        else:
            stdin,stdout,stderr = sshClient.exec_command(cmd)
            print("one remote clienthive startted")
            output = stdout.read()


    def checkResult(self,objid,response):
        if self.checkobjs[objid].bodyequal and self.checkobjs[objid].bodyequal != response["Body"]:
            return False,"check body does not equal responseBody:%s" %response["Body"]

        if self.checkobjs[objid].headerequal and self.checkobjs[objid].headerequal != response["Header"]:
            return False,"check header does not equal responseHeader:%s" %response["Header"]

        if self.checkobjs[objid].bodycontains and not self.checkobjs[objid].bodyusereg:
            if self.checkobjs[objid].bodycontains not in response["Body"]:
                return False,"response body does not contain checkbody:%s" %response["Body"]
        elif self.checkobjs[objid].bodycontains and self.checkobjs[objid].bodyusereg:
            m = re.search(r"%s" %self.checkobjs[objid].bodycontains,response["Body"])
            if not m:
                return False,"response body does not contain checkbody:%s" %response["Body"]

        if self.checkobjs[objid].headercontains and not self.checkobjs[objid].headerusereg:
            if self.checkobjs[objid].headercontains not in response["Header"]:
                return False,"response header does not contain check header:%s" %response["Header"]
        elif self.checkobjs[objid].headercontains and self.checkobjs[objid].headerusereg:
            m = re.search(r"%s" %self.checkobjs[objid].headercontains,response["Header"])
            if not m:
                return False,"response header does not contain check header:%s" %response["Header"]

        if self.checkobjs[objid].bodylengthtype:
            if self.checkobjs[objid].bodylengthtype == "0":
                if len(response["Body"]) > self.checkobjs[objid].bodylength:
                    return False,"response body length(%s) is no less than %s" %(len(response["Body"]),self.checkobjs[objid].bodylength)
            elif self.checkobjs[objid].bodylengthtype == "1":
                if len(response["Body"]) != self.checkobjs[objid].bodylength:
                    return False,"response body length(%s) does not equal %s" %(len(response["Body"]),self.checkobjs[objid].bodylength)
            else:
                if len(response["Body"]) < self.checkobjs[objid].bodylength:
                    return False,"response body length(%s) is no bigger than %s" %(len(response["Body"]),self.checkobjs[objid].bodylength)

        if self.checkobjs[objid].headerlengthtype:
            if self.checkobjs[objid].headerlengthtype == "0":
                if len(response["Header"]) > self.checkobjs[objid].headerlength:
                    return False,"response header length(%s) is no less than %s" %(len(response["Header"]),self.checkobjs[objid].headerlength)
            elif self.checkobjs[objid].headerlengthtype == "1":
                if len(response["Header"]) != self.checkobjs[objid].headerlength:
                    return False,"response header length(%s) does not equal %s" %(len(response["Header"]),self.checkobjs[objid].headerlength)
            else:
                if len(response["Header"]) < self.checkobjs[objid].headerlength:
                    return False,"response header length(%s) is no bigger than %s" %(len(response["Header"]),self.checkobjs[objid].headerlength)

        return True,None

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
        bee = gnsq.Reader("%s_success" %self.id,"goodBee","%s:4150" %self.config.nsq_host)
        self.analysisBees.append(bee)

        @bee.on_message.connect
        def handler(bee, message):
            self.samples += 1
            messagebody = message.body.decode()
            ms = json.loads(messagebody)

            elapsed = 0
            checkpass,errorMsg = True,""
            for i,m in enumerate(ms):
                elapsed += m["Elapsed"]
                cp,err = self.checkResult(i,m)
                if not cp:
                    checkpass = False
                    errorMsg += "%s," %err
                else:
                    errorMsg += ","

            self.totalelapsed += elapsed

            if not self.min_elapsed or elapsed < self.min_elapsed:
                self.min_elapsed = elapsed

            if not self.max_elapsed or elapsed > self.max_elapsed:
                self.max_elapsed = elapsed
            
            if not checkpass:
                self.assertionErrors += 1
                self.redisclient.lpush("%s_assertionError"%self.id,errorMsg)

            self.redisclient.lpush("%s_elapsed" %self.id,elapsed)

        bee.start()


    def collectBadHoney(self,honeyid):
        bee = gnsq.Reader("%s_failed" %self.id,"badBee","%s:4150" %self.config.nsq_host)
        self.analysisBees.append(bee)
        @bee.on_message.connect
        def handler(bee, message):
            self.samples += 1
            self.errors += 1

            m = message.body.decode()

            etype = None

            re_conn = re.search(r"Client\.Timeout",m)
            re_resp = re.search(r"net\/http\: timeout",m)

            if re_conn:
                self.connectionTimeouts += 1
                etype = "connectTimeout"
            elif re_resp:
                self.responseTimeouts += 1
                etype = "responseTimeout"
            else:
                self.unknownErrors += 1
                etype = "unknownError"

            #Error分类，存错误信息
            self.redisclient.lpush("%s.%s"%(self.id,etype),m)

        bee.start()

    @property
    def honeyCount(self):
        url = "http://%s:4171/api/nodes/nsp:4151" %self.config.nsq_host
        topics = requests.get(url).json()["topics"]
        message_count = 0
        for topic in topics:
            if topic["topic_name"] in ["%s_success" %self.id,"%s_failed" %self.id]:
                message_count += topic["message_count"]

        return message_count

    @property
    def progress(self):
        elapsed = time.time() - self.starttime
        try:
            avg_elapsed = self.totalelapsed / (self.samples - self.errors)
            error_percent = round((self.errors+self.assertionErrors) / self.samples,4) * 100
        except ZeroDivisionError:
            avg_elapsed = 0
            error_percent = 0

        throught = (self.samples-self.errors) / (elapsed if elapsed < self.looptime else self.looptime)

        return {
        "p":int(elapsed) if elapsed < self.looptime else self.looptime,#progress
        "e":int(elapsed) if elapsed < self.looptime else self.looptime,#elapsed
        "s":2 if self.end else 1,#status
        "l":self.looptime,#looptime
        "sas":self.samples,#samples
        "min_e":round(self.min_elapsed,3),#min_elapsed
        "max_e":round(self.max_elapsed,3),#max_elapsed
        "avg_e":round(avg_elapsed,3),#average_elapsed
        "toh":round(throught,2),#throught
        "es":self.errors+self.assertionErrors,#errors
        "e_c":self.connectionTimeouts,#error_connect
        "e_r":self.responseTimeouts,#error_resp
        "e_u":self.unknownErrors,#error_unknown
        "e_a":self.assertionErrors,#error_assert
        "e_p":round(error_percent,2)#error_percent
        }

    def dumpStatus(self):
        while not self.end:
            self.statusController.set(self.id,self.progress)
            time.sleep(1.5)

        self.statusController.set(self.id,self.progress)













