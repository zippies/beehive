import requests,os
from threading import Thread

ip = os.environ.get("NSQ_HOST")

delurl = "http://%s:4171/api/topics/%s"
r = requests.get("http://%s:4171/api/nodes" %ip).json()["nodes"][0]["topics"]

threadlist = []

print(len(r))
for topic in r:
	url = delurl %(ip,topic["topic"])
	t = Thread(target=requests.delete,args=(url,))
	threadlist.append(t)

for t in threadlist:
	t.start()

for t in threadlist:
	t.join()

print("end")
