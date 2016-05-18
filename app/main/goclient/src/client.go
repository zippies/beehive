package main

import (
	"bytes"
	//"crypto/rand"
	"encoding/json"
	"fmt"
	"io/ioutil"
	"log"
	//"math/big"
	"net"
	"net/http"
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

func countTime() {
	starttime := time.Now()
	for {
		time.Sleep(3 * 1e9)
		println("time elapsed:", int(time.Now().Sub(starttime).Seconds()))
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
	failOnError(err, "udp baidu.com:80 failed")
	defer conn.Close()
	return strings.Split(conn.LocalAddr().String(), ":")[0]
}

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

func sendResult(goroutine_id int,
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
		report.Goroutine_id = goroutine_id
		report.ErrorMsg = error.Error()
		report.StatusCode = -1
		topic = "failed"
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
		report.Goroutine_id = goroutine_id
		topic = "success"
		defer resp.Body.Close()
	}
	//println(report.body)
	body, err := json.Marshal(&report)
	failOnError(err, "Failed to Marshall")
	//	i, _ := rand.Int(rand.Reader, big.NewInt(int64(rannum)))
	//	time.Sleep(time.Duration(i.Int64()) * time.Second)

	err = worker.Publish(topic, []byte(body))
	failOnError(err, "Failed to publish a message")
	//println(body)
	group_report.Done()
}

func startClient(
	goroutine_id int,
	client *http.Client,
	url string,
	method string,
	header map[string]string,
	data []byte,
	looptime int,
	worker *nsq.Producer,
	ip string) {

	for start := time.Now(); int(time.Now().Sub(start).Seconds()) < looptime; {
		req, e := http.NewRequest(method, url, bytes.NewReader(data))
		failOnError(e, "NewRequest failed")
		for key, value := range header {
			req.Header.Set(key, value)
		}
		start_time := time.Now()
		resp, err := client.Do(req)
		end_time := time.Now()

		group_report.Add(1)
		go sendResult(goroutine_id, url, method, ip, worker, resp, err, start_time, end_time)

	}
	group_client.Done()
}

func main() {
	config := nsq.NewConfig()
	config.DialTimeout = 5 * 1e9
	config.WriteTimeout = 60 * 1e9
	config.HeartbeatInterval = 10 * 1e9

	worker, err := nsq.NewProducer("120.26.203.88:4150", config)
	failOnError(err, "Failed to newProducer")

	//connect to redis
	redis_conn, err := redis.Dial("tcp", "120.26.203.88:6379")
	failOnError(err, "Failed to connect to redis")
	defer redis_conn.Close()

	//获取本机ip
	ip := getLocalIp()

	//记录运行时间
	start := time.Now()

	//初始化并发量
	var con int

	//初始化并发时间
	var looptime int

	//死循环，等待redis中任务状态为1
	for {
		end := time.Now()
		duration := end.Sub(start).Seconds()
		if duration > 60 {
			fmt.Println("timeout")
			break
		}

		start_redis := time.Now()
		concurrent, _ := redis_conn.Do("hget", ip, "concurrent")
		method, _ := redis_conn.Do("get", "method")
		url, _ := redis_conn.Do("get", "url")
		loop, _ := redis_conn.Do("get", "looptime")

		redis_header, _ := redis_conn.Do("hget", ip, "header")
		redis_data, _ := redis_conn.Do("hget", ip, "data")

		redis_cont, _ := redis_conn.Do("get", "connectTimeout")
		redis_resp, _ := redis_conn.Do("get", "responseTimeout")

		redis_delay, _ := redis_conn.Do("get", "startDelay")
		redis_status, err := redis_conn.Do("get", "status")
		failOnError(err, "查询出错")

		end_redis := time.Now()

		//打印redis查询时间
		fmt.Println("query time:", end_redis.Sub(start_redis).Seconds())

		//redis中status值未初始化
		if redis_status == nil {
			continue
		}

		//redis中status为1时，读取concurrent值，启动并发任务 startClient() 并等待goroutine结束
		if string(redis_status.([]byte)) == "1" {
			var header map[string]string
			var tmpdata map[string]interface{}
			var conn_timeout, resp_timeout time.Duration
			var conc_delay float64

			if redis_header != nil {
				err = json.Unmarshal(redis_header.([]byte), &header)
				if err != nil {
					println("Unmarshal header error", err)
					continue
				}
			}

			if redis_data != nil {
				err = json.Unmarshal(redis_data.([]byte), &tmpdata)
				if err != nil {
					println("Unmarshal data error", err)
					continue
				}
			}

			data, err := json.Marshal(tmpdata)
			if err != nil {
				println("Marshal data error", err)
				continue
			} else {
				println("data", len(data))
			}

			if redis_delay == nil {
				conc_delay = float64(0)
			} else {
				t, _ := strconv.Atoi(string(redis_delay.([]byte)))
				conc_delay = float64(t) * 1e9
			}

			if redis_cont == nil {
				conn_timeout = time.Duration(5)
			} else {
				t, _ := strconv.Atoi(string(redis_cont.([]byte)))
				conn_timeout = time.Duration(t)
			}

			if redis_resp == nil {
				resp_timeout = time.Duration(10)
			} else {
				t, _ := strconv.Atoi(string(redis_resp.([]byte)))
				resp_timeout = time.Duration(t)
			}

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

			if concurrent == nil {
				fmt.Println("concurrent not set")
				continue
			} else if method == nil {
				fmt.Println("method not set")
				continue
			} else if url == nil {
				fmt.Println("url not set")
				continue
			} else if loop == nil {
				fmt.Println("looptime not set")
				continue
			} else {
				fmt.Println("concurrent:", string(concurrent.([]byte)))

				con, _ = strconv.Atoi(string(concurrent.([]byte)))

				looptime, _ = strconv.Atoi(string(loop.([]byte)))

				rannum = (con / 10) * (looptime / 10)
				println("rannum", rannum)
				st := time.Now()
				for i := 0; i < con; i++ {
					group_client.Add(1)
					time.Sleep(time.Duration(conc_delay/float64(con)) * time.Nanosecond)
					go startClient(i, client, string(url.([]byte)), string(method.([]byte)), header, data, looptime, worker, ip)
				}
				go countTime()
				println("all clients startted ,looptime", looptime)

				group_client.Wait()
				client_end := time.Now()
				println("all client done during", int(client_end.Sub(st).Seconds()))

				group_report.Wait()
				et := time.Now()
				println("all workers done during", int(et.Sub(st).Seconds()), "seconds")

				worker.Stop()

				redis_conn.Do("hset", ip, "status", 1)

				break
			}
		}
	}
	println("end here")

}
