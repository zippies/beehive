package main

import (
	"encoding/json"
	"log"
	"net/http"
	"time"

	"github.com/nsqio/go-nsq"
)

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

func main() {
	c := make(chan int)
	config := nsq.NewConfig()
	consumer, err := nsq.NewConsumer("success", "consumer", config)
	if err != nil {
		log.Println(err.Error())
	}

	consumer.AddHandler(nsq.HandlerFunc(func(message *nsq.Message) error {
		var report Report
		c <- 1
		err = json.Unmarshal(message.Body, &report)
		if err != nil {
			log.Println("unmarshal failed")
		} else {
			log.Printf("Got a message:%v", report.Body)
		}
		return nil
	}))

	err = consumer.ConnectToNSQD("120.26.203.88:4150")
	if err != nil {
		log.Println("Connect to NSQD failed", err.Error())
	}

	var timeoutCount int

	for {
		select {
		case i := <-c:
			timeoutCount = 0
		case <-time.After(time.Duration(2) * time.Second):
			timeoutCount++
		}
		if timeoutCount > 10 {
			break
		}
	}
}
