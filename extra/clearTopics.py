import requests
from threading import Thread

delurl = "http://104.236.5.165:4171/api/topics/%s"
r = requests.get("http://104.236.5.165:4171/api/nodes").json()["nodes"][0]["topics"]

threadlist = []

print(len(r))
for topic in r:
	url = delurl %topic["topic"]
	t = Thread(target=requests.delete,args=(url,))
	threadlist.append(t)

for t in threadlist:
	t.start()

for t in threadlist:
	t.join()

print("end")