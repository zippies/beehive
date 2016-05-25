package main

import (
	"bytes"
	"container/ring"
	"encoding/json"
	"fmt"
	"io/ioutil"
	"log"
	"math/rand"
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

func countTime(redis_conn redis.Conn, key string) {
	for {
		time.Sleep(2 * 1e9)
		status, err := redis_conn.Do("hget", key, "status")
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
	url string,
	method string,
	ip string,
	worker *nsq.Producer,
	resp *http.Response,
	error error,
	starttime time.Time,
	endtime time.Time) {

	var report Report
	var topic string

	if error != nil {
		report.Method = method
		report.Url = url
		report.Elapsed = endtime.Sub(starttime).Seconds()
		report.Machine_ip = ip
		report.ErrorMsg = error.Error()
		report.StatusCode = -1
		topic = fmt.Sprintf("failed-%v", missionid)
	} else {
		report.Method = method
		report.Url = url
		report.StatusCode = resp.StatusCode
		report.Elapsed = endtime.Sub(starttime).Seconds()
		result, err := ioutil.ReadAll(resp.Body)
		if result != nil {
			report.Body = string(result)
		} else {
			report.Body = "body is null:" + err.Error()
		}
		report.ContentLength = len(result)
		report.Header = resp.Header
		report.Cookies = resp.Cookies()
		report.Machine_ip = ip
		topic = fmt.Sprintf("success-%v", missionid)
		defer resp.Body.Close()
	}

	body, err := json.Marshal(&report)
	failOnError(err, "Failed to Marshall")

	err = worker.Publish(topic, []byte(body))
	failOnError(err, "Failed to publish a message")

	group_report.Done()
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

func dealRandom(value interface{}) []byte {
	tmpstr := fmt.Sprint(value)
	reg_phone := regexp.MustCompile(`{{ *randomPhone\(\) *}}`)
	reg_int := regexp.MustCompile(`{{ *randomInt\((\d+),(\d+)\) *}}`)

	len_ranint := len(reg_int.FindAllString(tmpstr, -1))

	for i := 0; i < len_ranint; i++ {
		matchlist := reg_int.FindStringSubmatch(tmpstr)
		//nums := strings.Split(strings.Split(strings.Split(matchstr, "randomInt(")[1], ")")[0], ",")
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

	return []byte(tmpstr)
}

func startClient(
	missionid string,
	client *http.Client,
	url string,
	method string,
	header map[string]string,
	looptime int,
	worker *nsq.Producer,
	ip string) {

	for start := time.Now(); int(time.Now().Sub(start).Seconds()) < looptime; {
		dataGenerator = dataGenerator.Next()
		data := dealRandom(dataGenerator.Value)
		req, e := http.NewRequest(method, url, bytes.NewReader(data))
		failOnError(e, "Failed to newRequest")
		for key, value := range header {
			req.Header.Set(key, value)
		}
		start_time := time.Now()
		resp, err := client.Do(req)
		end_time := time.Now()

		group_report.Add(1)
		go sendResult(missionid, url, method, ip, worker, resp, err, start_time, end_time)

	}
	group_client.Done()
}

func main() {
	config := nsq.NewConfig()
	config.DialTimeout = 5 * 1e9
	config.WriteTimeout = 60 * 1e9
	config.HeartbeatInterval = 10 * 1e9

	nsqd_addr, redis_addr, missionid := os.Args[1], os.Args[2], os.Args[3]
	worker, err := nsq.NewProducer(nsqd_addr, config)
	//worker, err := nsq.NewProducer("104.236.5.165:4150", config)
	failOnError(err, "Failed to newProducer")

	//connect to redis
	//redis_conn, err := redis.Dial("tcp", "127.0.0.1:6379")
	redis_conn, err := redis.Dial("tcp", redis_addr)
	failOnError(err, "Failed to connect to redis")
	defer redis_conn.Close()

	//获取本机ip
	ip := getLocalIp()

	key := fmt.Sprintf("%v.%v", missionid, ip)

	//初始化并发量
	var con int
	var looptime int
	var header map[string]string
	var tmpdata map[string]interface{}
	var conn_timeout, resp_timeout time.Duration
	var conc_delay float64
	var dataCount int

	method, err := redis_conn.Do("hget", key, "method")
	failOnError(err, "Failed to query Redis")
	url, err := redis_conn.Do("hget", key, "url")
	failOnError(err, "Failed to query Redis")
	loop, err := redis_conn.Do("hget", key, "looptime")
	failOnError(err, "Failed to query Redis")
	redis_cont, err := redis_conn.Do("hget", key, "connectTimeout")
	failOnError(err, "Failed to query Redis")
	redis_resp, err := redis_conn.Do("hget", key, "responseTimeout")
	failOnError(err, "Failed to query Redis")
	redis_delay, err := redis_conn.Do("hget", key, "startDelay")
	failOnError(err, "Failed to query Redis")
	concurrent, err := redis_conn.Do("hget", key, "concurrent")
	failOnError(err, "Failed to query Redis")
	redis_header, err := redis_conn.Do("hget", key, "header")
	failOnError(err, "Failed to query Redis")
	redis_data, err := redis_conn.Do("hget", key, "data")
	failOnError(err, "Failed to query Redis")

	if redis_header != nil {
		err = json.Unmarshal(redis_header.([]byte), &header)
		failOnError(err, "Failed to Unmarshal header")
	}

	if redis_data != nil {
		err = json.Unmarshal(redis_data.([]byte), &tmpdata)
		failOnError(err, "Failed to Unmarshal redis-data to map-data")
	}

	data, err := json.Marshal(tmpdata)
	failOnError(err, "Failed to Marshal map-data")

	data_count, err := redis_conn.Do("get", fmt.Sprintf("dataCount-%v", missionid))
	failOnError(err, "Failed to query Redis")
	if data_count == nil {
		dataCount = 1
	} else {
		dataCount, err = strconv.Atoi(string(data_count.([]byte)))
		failOnError(err, "Failed to parse dataCount<string> to int")
	}

	dataGenerator = ring.New(dataCount)
	s_data := string(data)

	reg_file := regexp.MustCompile(`{{ *file\[(\d+)\] *}}`)

	len_ranint := len(reg_file.FindAllString(s_data, -1))

	if len_ranint > 0{
		for i := 0; i < dataCount; i++ {
			matchlist := reg_file.FindStringSubmatch(s_data)
			
			indexdata, err := redis_conn.Do("lindex", fmt.Sprintf("filedata-%v", missionid), i)
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
	}else{
		dataGenerator.Value = s_data
		dataGenerator = dataGenerator.Next()
	}


	// for i := 0; i < dataCount; i++ {
	// 	if strings.Contains(s_data, "{{file[") {
	// 		indexdata, err := redis_conn.Do("lindex", fmt.Sprintf("filedata-%v", missionid), i)
	// 		failOnError(err, "Failed to query Redis")
	// 		values := strings.Split(string(indexdata.([]byte)), " ")
	// 		r_data := s_data
	// 		for k, v := range values {
	// 			r_data = strings.Replace(r_data, fmt.Sprintf("{{file[%v]}}", k), v, -1)
	// 		}
	// 		dataGenerator.Value = r_data
	// 		dataGenerator = dataGenerator.Next()
	// 	} else {
	// 		dataGenerator.Value = s_data
	// 		dataGenerator = dataGenerator.Next()
	// 	}
	// }

	if redis_delay == nil {
		conc_delay = float64(0)
	} else {
		t, _ := strconv.Atoi(string(redis_delay.([]byte)))
		conc_delay = float64(t) * 1e9
	}

	if redis_cont == nil {
		conn_timeout = time.Duration(5)
	} else {
		t, err := strconv.Atoi(string(redis_cont.([]byte)))
		failOnError(err, "Failed to parse requestTimeout<string> to int")
		conn_timeout = time.Duration(t)
	}

	if redis_resp == nil {
		resp_timeout = time.Duration(10)
	} else {
		t, err := strconv.Atoi(string(redis_resp.([]byte)))
		failOnError(err, "Failed to parse responseTimeout<string> to int")
		resp_timeout = time.Duration(t)
	}

	con, err = strconv.Atoi(string(concurrent.([]byte)))
	failOnError(err, "Failed to parse concurrent<string> to int")
	fmt.Println("concurrent:", con)

	looptime, err = strconv.Atoi(string(loop.([]byte)))
	failOnError(err, "Failed to parse looptime<string> to int")

	//初始化http.client
	client := &http.Client{
		Transport: &http.Transport{
			Dial: func(netw, addr string) (net.Conn, error) {
				conn, err := net.DialTimeout(netw, addr, time.Second*conn_timeout)
				if err != nil {
					return nil, err
				}
				return conn, nil
			},
			ResponseHeaderTimeout: time.Second * resp_timeout,
		},
	}
	//连接超时设置
	client.Timeout = conn_timeout * time.Second

	_, err = redis_conn.Do("hset", key, "status", 1)
	failOnError(err, "Failed to set Redis status to 1")

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

		redis_status, err := redis_conn.Do("get", fmt.Sprintf("status-%v", missionid))
		failOnError(err, "Failed to query Redis")

		if redis_status == nil {
			continue
		}

		//redis中status为1时，启动并发任务 startClient() 并等待goroutine结束
		if string(redis_status.([]byte)) == "1" {

			st := time.Now()
			for i := 0; i < con; i++ {
				group_client.Add(1)
				time.Sleep(time.Duration(conc_delay/float64(con)) * time.Nanosecond)
				go startClient(missionid, client, string(url.([]byte)), string(method.([]byte)), header, looptime, worker, ip)
			}
			go countTime(redis_conn, key)
			println("all clients startted ,looptime", looptime)

			group_client.Wait()
			client_end := time.Now()
			println("all client done during", int(client_end.Sub(st).Seconds()))

			group_report.Wait()
			et := time.Now()
			println("all workers done during", int(et.Sub(st).Seconds()), "seconds")

			worker.Stop()

			_, err = redis_conn.Do("hset", key, "status", 2)
			failOnError(err, "Failed to set Redis status to 2")
			break

		}
	}
	println("end here")

}
