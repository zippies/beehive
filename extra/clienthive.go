package main

import (
	"bytes"
	"container/ring"
	"encoding/json"
	"fmt"
	"io/ioutil"
	"log"
	"math/rand"
	"mime/multipart"
	"net"
	"net/http"
	"os"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/garyburd/redigo/redis"
	"github.com/nsqio/go-nsq"
)

var rannum int
var group_report sync.WaitGroup
var group_client sync.WaitGroup
var dataGenerator *ring.Ring

func countTime(redis_conn redis.Conn, missionid string) {
	for {
		time.Sleep(2 * 1e9)
		status, err := redis_conn.Do("get", fmt.Sprintf("%v_status", missionid))
		failOnError(err, "Failed to query redis")
		currentStatus, err := strconv.Atoi(string(status.([]byte)))
		failOnError(err, "Failed to convert <status>String to Int ")
		if currentStatus == -1 {
			os.Exit(-1)
		}
	}
}

func failOnError(err error, msg string) {
	if err != nil {
		log.Fatalf("%s: %s", msg, err)
		panic(fmt.Sprintf("%s: %s", msg, err))
	}
}

func getLocalIp() string {
	conn, err := net.Dial("udp", "baidu.com:80")
	failOnError(err, "Failed udp baidu.com:80")
	defer conn.Close()
	return strings.Split(conn.LocalAddr().String(), ":")[0]
}

func randomInt(min int, max int) int {
	r := rand.New(rand.NewSource(time.Now().UnixNano()))
	ranint := r.Intn(max-min) + min
	return ranint
}

func randomPhone() string {
	phoneHead := []int{134, 135, 136, 137, 138, 139, 150, 151, 152, 157, 158, 159, 182, 183, 184, 187, 188, 178, 147, 130, 131, 132, 155, 156, 185, 186, 176, 145, 133, 153, 180, 181, 189, 177}
	ranindex := randomInt(0, len(phoneHead))
	return fmt.Sprintf("%v%v", phoneHead[ranindex], randomInt(10000000, 19999999))
}

func dealUrl(url string,envmap map[string]string) string{
	reg_env := regexp.MustCompile(`{{ *env\((.+)\) *}}`)
	len_env := len(reg_env.FindAllString(url, -1))
	for i := 0; i < len_env; i++ {
		matchlist := reg_env.FindStringSubmatch(url)
		name := matchlist[1]
		url = strings.Replace(url, matchlist[0], fmt.Sprintf("%v", envmap[name]), 1)
	}

	return url
}

func dealRandom(value interface{}, envmap map[string]string) []byte {
	tmpstr := fmt.Sprint(value)
	reg_phone := regexp.MustCompile(`{{ *randomPhone\(\) *}}`)
	reg_int := regexp.MustCompile(`{{ *randomInt\((\d+),(\d+)\) *}}`)
	reg_env := regexp.MustCompile(`{{ *env\((.+)\) *}}`)

	len_ranint := len(reg_int.FindAllString(tmpstr, -1))

	for i := 0; i < len_ranint; i++ {
		matchlist := reg_int.FindStringSubmatch(tmpstr)
		min, err := strconv.Atoi(matchlist[1])
		failOnError(err, "Failed:randomInt only support int params")
		max, err := strconv.Atoi(matchlist[2])
		failOnError(err, "Failed:randomInt only support int params")
		ranint := randomInt(min, max)
		tmpstr = strings.Replace(tmpstr, matchlist[0], fmt.Sprintf("%v", ranint), 1)
	}

	len_ranphone := len(reg_phone.FindAllString(tmpstr, -1))

	for i := 0; i < len_ranphone; i++ {
		matchstr := reg_phone.FindString(tmpstr)
		ranphone := randomPhone()
		tmpstr = strings.Replace(tmpstr, matchstr, fmt.Sprintf("%v", ranphone), 1)
	}

	len_env := len(reg_env.FindAllString(tmpstr, -1))

	for i := 0; i < len_env; i++ {
		matchlist := reg_env.FindStringSubmatch(tmpstr)
		name := matchlist[1]
		tmpstr = strings.Replace(tmpstr, matchlist[0], fmt.Sprintf("%v", envmap[name]), 1)
	}

	return []byte(tmpstr)
}

func startClient(
	missionid string,
	requests []Request,
	looptime int,
	worker *nsq.Producer,
	ip string) {

	for start := time.Now(); int(time.Now().Sub(start).Seconds()) < looptime; {
		envmap := make(map[string]string)

		for index, request := range requests {
			var req *http.Request
			var e error

			dataGenerator = request.dataGenerator.Next()
			data := dealRandom(dataGenerator.Value, envmap)
			request.url = dealUrl(request.url, envmap)

			if request.filetype != 1 {
				var tmp map[string]string
				var slice []string
				if request.method == "GET"{
					err := json.Unmarshal(data,&tmp)
					failOnError(err, "Failed to Unmarshal data")
					for key,value := range tmp{
						slice = append(slice,fmt.Sprintf("%v=%v",key,value))
					}
					request.url = request.url+"?"+strings.Join(slice,"&")
					data = []byte("")
				}
				req, e = http.NewRequest(request.method, request.url, bytes.NewReader(data))
				failOnError(e, "Failed to newRequest,filetype != 1")
				for key, value := range request.header {
					req.Header.Set(key, value)
				}
			} else {
				var dataobj map[string]string
				body := new(bytes.Buffer)
				w := multipart.NewWriter(body)
				content_type := w.FormDataContentType()
				e := json.Unmarshal(data, &dataobj)
				failOnError(e, "Failed to Unmarshal data")
				for key, value := range dataobj {
					w.WriteField(key, value)
				}
				file, _ := w.CreateFormFile(request.filefield, request.filename)
				file.Write(request.filecontent)
				w.Close()
				req, e = http.NewRequest(request.method, request.url, body)
				failOnError(e, "Failed to newRequest,filetype == 1")
				req.Header.Set("Content-Type", content_type)
				for key, value := range request.header {
					req.Header.Set(key, value)
				}
			}
			start_time := time.Now()
			resp, err := request.client.Do(req)
			end_time := time.Now()
			
			requests[index].url = request.url
			requests[index].resp = resp
			requests[index].err = err
			requests[index].elapsed = end_time.Sub(start_time).Seconds()
			if err != nil {
				fmt.Println("error occured")
				break
			}
			for _, env := range request.envs {
				var datastring string
				if env.source == "header" {
					databytes, err := json.Marshal(resp.Header)
					failOnError(err, "Failed to Marshal resp.Header")
					datastring = string(databytes)
				} else {
					databytes, err := ioutil.ReadAll(resp.Body)
					failOnError(err, "Failed to read resp.Body")
					datastring = string(databytes)
				}
				regx := regexp.MustCompile(env.regx)
				envmap[env.name] = regx.FindStringSubmatch(datastring)[1]
			}
			//if index != 0{
			//	tmp,_ := ioutil.ReadAll(resp.Body)
			//	fmt.Println(index,request.method,request.url,resp.StatusCode,string(data),string(tmp))
			//}
		}
		group_report.Add(1)
		go sendResult(missionid, ip, worker, requests)
	}
	group_client.Done()
}

type Report struct {
	Url           string
	Method        string
	Elapsed       float64
	Machine_ip    string
	ErrorMsg      string
	StatusCode    int
	Body          string
	ContentLength int
	Header        http.Header
	Cookies       []*http.Cookie
}

func sendResult(missionid string,
	ip string,
	worker *nsq.Producer,
	requests []Request) {

	var reports []Report

	topic := fmt.Sprintf("%v_success", missionid)

	for _, request := range requests {
		var report Report

		if request.err != nil {
			report.Method = request.method
			report.Url = request.url
			report.Elapsed,_ = strconv.ParseFloat(fmt.Sprintf("%.0f",request.elapsed),64)
			report.Machine_ip = ip
			report.ErrorMsg = request.err.Error()
			report.StatusCode = -1
			topic = fmt.Sprintf("%v_failed", missionid)
		} else {
			report.Method = request.method
			report.Url = request.url
			report.StatusCode = request.resp.StatusCode
			report.Elapsed = request.elapsed
			result, err := ioutil.ReadAll(request.resp.Body)
			if result != nil {
				report.Body = string(result)
			} else {
				report.Body = "body is null:" + err.Error()
			}
			report.ContentLength = len(result)
			report.Header = request.resp.Header
			report.Cookies = request.resp.Cookies()
			report.Machine_ip = ip
			defer request.resp.Body.Close()
		}
		reports = append(reports, report)
	}
	body, err := json.Marshal(&reports)
	failOnError(err, "Failed to Marshall reports")
	err = worker.Publish(topic, []byte(body))
	failOnError(err, "Failed to publish a message")
	group_report.Done()
}

type Env struct {
	source string
	name   string
	regx   string
}

type Request struct {
	url           string
	method        string
	client        *http.Client
	header        map[string]string
	dataGenerator *ring.Ring
	filetype      int
	filecontent   []byte
	filefield     string
	filename      string
	envcount      int
	envs          []Env
	resp          *http.Response
	err           error
	elapsed       float64
}

func main() {
	config := nsq.NewConfig()
	config.DialTimeout = 5 * 1e9
	config.WriteTimeout = 60 * 1e9
	config.HeartbeatInterval = 10 * 1e9
	//missionid := "3"
	nsqd_addr, redis_addr, missionid := os.Args[1], os.Args[2], os.Args[3]
	worker, err := nsq.NewProducer(nsqd_addr, config)
	//worker, err := nsq.NewProducer("104.236.5.165:4150", config)
	failOnError(err, "Failed to newProducer")

	//connect to redis
	//redis_conn, err := redis.Dial("tcp", "localhost:6379")
	redis_conn, err := redis.Dial("tcp", redis_addr)
	failOnError(err, "Failed to connect to redis")
	defer redis_conn.Close()

	//获取本机ip
	ip := getLocalIp()
	//ip := "198.199.76.200"
	id_ip := fmt.Sprintf("%v_%v", missionid, ip)

	//初始化并发量
	var con int
	var looptime int
	var start_delay float64

	concurrent, err := redis_conn.Do("hget", id_ip, "concurrent")
	failOnError(err, "Failed to query Redis")

	redis_delay, err := redis_conn.Do("get", fmt.Sprintf("%v_startdelay", missionid))
	failOnError(err, "Failed to query Redis")

	redis_looptime, err := redis_conn.Do("get", fmt.Sprintf("%v_looptime", missionid))
	failOnError(err, "Failed to query Redis")

	if redis_delay == nil {
		start_delay = float64(0)
	} else {
		t, _ := strconv.Atoi(string(redis_delay.([]byte)))
		start_delay = float64(t) * 1e9
	}

	con, err = strconv.Atoi(string(concurrent.([]byte)))
	failOnError(err, "Failed to parse concurrent<string> to int")

	looptime, err = strconv.Atoi(string(redis_looptime.([]byte)))
	failOnError(err, "Failed to parse looptime<string> to int")

	redis_apicount, err := redis_conn.Do("llen", fmt.Sprintf("%v_urls", missionid))
	failOnError(err, "Failed to query Redis")

	apicount, ok := redis_apicount.(int64)
	if !ok {
		fmt.Println("Failed to parse redis_apicount<interface> to int64")
	}

	requests := []Request{}

	for i := 0; i < int(apicount); i++ {
		var request Request
		var header map[string]string
		var tmpdata map[string]interface{}

		url, err := redis_conn.Do("lindex", fmt.Sprintf("%v_urls", missionid), i)
		failOnError(err, "Failed to query Redis,url")
		method, err := redis_conn.Do("lindex", fmt.Sprintf("%v_methods", missionid), i)
		failOnError(err, "Failed to query Redis,method")
		resptimeout, err := redis_conn.Do("lindex", fmt.Sprintf("%v_resptimeouts", missionid), i)
		failOnError(err, "Failed to query Redis,resptimeout")
		conntimeout, err := redis_conn.Do("lindex", fmt.Sprintf("%v_conntimeouts", missionid), i)
		failOnError(err, "Failed to query Redis,conntimeout")
		redis_header, err := redis_conn.Do("lindex", fmt.Sprintf("%v_headers", missionid), i)
		failOnError(err, "Failed to query Redis,redis_header")
		redis_data, err := redis_conn.Do("lindex", fmt.Sprintf("%v_datas", missionid), i)
		failOnError(err, "Failed to query Redis,redis_data")
		redis_filetype, err := redis_conn.Do("lindex", fmt.Sprintf("%v_filetypes", missionid), i)
		failOnError(err, "Failed to query Redis,redis_filetype")
		redis_envcount, err := redis_conn.Do("lindex", fmt.Sprintf("%v_envcounts", missionid), i)
		failOnError(err, "Failed to query Redis,redis_envcounts")

		request.url = string(url.([]byte))
		request.method = string(method.([]byte))

		filetype, err := strconv.Atoi(string(redis_filetype.([]byte)))
		failOnError(err, "Failed to parse redis_filetype<string> to int")

		request.filetype = filetype

		envcount, err := strconv.Atoi(string(redis_envcount.([]byte)))
		failOnError(err, "Failed to parse redis_envcount<string> to int")

		request.envcount = envcount
		for j := 0; j < envcount; j++ {
			var env Env
			redis_envsource, err := redis_conn.Do("hget", fmt.Sprintf("%v_env_%v_%v", missionid, i, j), "source")
			failOnError(err, "Failed to query Redis,redis_envsource")
			redis_envname, err := redis_conn.Do("hget", fmt.Sprintf("%v_env_%v_%v", missionid, i, j), "name")
			failOnError(err, "Failed to query Redis,redis_envname")
			redis_envregx, err := redis_conn.Do("hget", fmt.Sprintf("%v_env_%v_%v", missionid, i, j), "regx")
			failOnError(err, "Failed to query Redis,redis_envregx")
			env.source = string(redis_envsource.([]byte))
			env.name = string(redis_envname.([]byte))
			env.regx = string(redis_envregx.([]byte))
			request.envs = append(request.envs, env)
		}

		conn_timeout, err := strconv.Atoi(string(conntimeout.([]byte)))
		failOnError(err, "Failed to parse conntimeout<string> to int")
		resp_timeout, err := strconv.Atoi(string(resptimeout.([]byte)))
		failOnError(err, "Failed to parse resptimeout<string> to int")

		if redis_header != nil {
			err = json.Unmarshal(redis_header.([]byte), &header)
			failOnError(err, "Failed to Unmarshal header")
		}

		request.header = header

		if redis_data != nil {
			err = json.Unmarshal(redis_data.([]byte), &tmpdata)
			failOnError(err, "Failed to Unmarshal redis-data to map-data")
		}

		data, err := json.Marshal(tmpdata)
		var dataCount int
		switch filetype {
		case 0:
			dataCount = 1
		case 1:
			dataCount = 1
			redis_filecontent, err := redis_conn.Do("hget", fmt.Sprintf("%v_file_%v", missionid, i), "filecontent")
			failOnError(err, "Failed to query Redis filecontent")
			redis_filefield, err := redis_conn.Do("hget", fmt.Sprintf("%v_file_%v", missionid, i), "filefield")
			failOnError(err, "Failed to query Redis field")
			redis_filename, err := redis_conn.Do("hget", fmt.Sprintf("%v_file_%v", missionid, i), "filename")
			failOnError(err, "Failed to query Redis filename")
			request.filecontent = redis_filecontent.([]byte)
			request.filefield = string(redis_filefield.([]byte))
			request.filename = string(redis_filename.([]byte))
		case 2:
			redis_datacount, err := redis_conn.Do("get", fmt.Sprintf("%v_datacount_%v", missionid, i))
			failOnError(err, "Failed to query Redis")
			dataCount, err = strconv.Atoi(string(redis_datacount.([]byte)))
			failOnError(err, "Failed to parse redis_datacount<string> to int")
		}

		dataGenerator = ring.New(dataCount)
		s_data := string(data)

		reg_file := regexp.MustCompile(`{{ *file\[(\d+)\] *}}`)

		len_ranint := len(reg_file.FindAllString(s_data, -1))

		if len_ranint > 0 {
			for c := 0; c < dataCount; c++ {
				matchlist := reg_file.FindStringSubmatch(s_data)

				indexdata, err := redis_conn.Do("lindex", fmt.Sprintf("%v_filedata_%v", missionid, i), c)
				failOnError(err, "Failed to query Redis")
				values := strings.Split(string(indexdata.([]byte)), " ")
				r_data := s_data
				for k, v := range values {
					undermatch := strings.Replace(matchlist[0], matchlist[1], fmt.Sprintf("%v", k), -1)
					r_data = strings.Replace(r_data, undermatch, v, -1)
				}

				dataGenerator.Value = r_data
				dataGenerator = dataGenerator.Next()
			}
		} else {
			dataGenerator.Value = s_data
			dataGenerator = dataGenerator.Next()
		}

		request.dataGenerator = dataGenerator

		//初始化http.client
		client := &http.Client{
			Transport: &http.Transport{
				Dial: func(netw, addr string) (net.Conn, error) {
					conn, err := net.DialTimeout(netw, addr, time.Second*time.Duration(conn_timeout))
					if err != nil {
						return nil, err
					}
					return conn, nil
				},
				ResponseHeaderTimeout: time.Second * time.Duration(resp_timeout),
			},
		}
		//连接超时设置
		client.Timeout = time.Duration(conn_timeout) * time.Second

		request.client = client
		requests = append(requests, request)
	}

	_, err = redis_conn.Do("hset", id_ip, "ready", 1)
	failOnError(err, "Failed to set Redis ready to 1")

	//记录运行时间
	start := time.Now()
	//死循环，等待redis中任务状态为1
	for {
		end := time.Now()
		duration := end.Sub(start).Seconds()
		if duration > 60 {
			fmt.Println("Failed to execute,timeout")
			break
		}

		redis_status, err := redis_conn.Do("get", fmt.Sprintf("%v_status", missionid))
		failOnError(err, "Failed to query Redis")

		if redis_status == nil {
			continue
		}

		//redis中status为1时，启动并发任务 startClient() 并等待goroutine结束
		if string(redis_status.([]byte)) == "1" {

			st := time.Now()
			for i := 0; i < con; i++ {
				group_client.Add(1)
				time.Sleep(time.Duration(start_delay/float64(con)) * time.Nanosecond)
				go startClient(missionid, requests, looptime, worker, ip)
			}
			go countTime(redis_conn, missionid)
			println("all clients startted ,looptime", looptime)

			group_client.Wait()
			client_end := time.Now()
			println("all client done during", int(client_end.Sub(st).Seconds()))

			group_report.Wait()
			et := time.Now()
			println("all workers done during", int(et.Sub(st).Seconds()), "seconds")

			worker.Stop()

			_, err = redis_conn.Do("set", fmt.Sprintf("%v_status", missionid), 2)
			failOnError(err, "Failed to set Redis status to 2")
			break

		}
	}
	println("end here")

}
