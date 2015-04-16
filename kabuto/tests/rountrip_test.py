'''
This test relies on the fact that both kabuto and ammonite services are running standalone
'''
import requests
import os
from kabuto.tests import sample_dockerfile
import time

ROOT_DIR = os.path.abspath(os.path.dirname(os.path.abspath(__file__)))
data = {'command': ['cp /inbox/file1.txt /outbox/output1.txt', "ll"]}
files = [("attachments", open(os.path.join(ROOT_DIR, "data", "file1.txt"), "rb")),
         ("attachments", open(os.path.join(ROOT_DIR, "data", "file2.txt"), "rb"))]
base_url = "http://127.0.0.1:5000"

r = requests.post('%s/login' % base_url, data={'login': 'me',
                                'password': 'Secret'})
c = r.cookies

r = requests.post('%s/image' % base_url,
                 data={'dockerfile': sample_dockerfile,
                       'name': 'hellozeworld'},
                  cookies=c)
image_id = r.json()['id']
print "created image"

r = requests.post('%s/pipeline' % base_url,
                 data={'name': 'my first pipeline'},
                 cookies=c)
pipeline_id = r.json()['id']
print "created pipeline"

data['image_id'] = image_id
r = requests.post('%s/pipeline/%s/job' % (base_url, pipeline_id),
                  data=data,
                  files=files,
                  cookies=c)

job_id = r.json()['id']
print "created job"

r = requests.post('%s/pipeline/%s/submit' % (base_url, pipeline_id),
                  cookies=c)
print "submitted job with following executions:"
for eid, state in r.json().iteritems():
    print "id: %s - state(%s)" % (eid, state)

r = requests.get('%s/execution/%s/logs' % (base_url, eid),
                  cookies=c)
print "Initial logs"
last_log_line = -1
for log_id, log in r.json().iteritems():
    last_log_line = log_id
    print log


def poll_for_state():
    r = requests.get('%s/execution/%s' % (base_url, eid),
                      cookies=c)
    return r.json()[unicode(eid)]

state = poll_for_state()
while not state == "done":
    print "state is %s" % state
    print "polling..."
    state = poll_for_state()
    time.sleep(1)

r = requests.get('%s/execution/%s/logs/%s' % (base_url, eid, last_log_line),
                  cookies=c)
print "Follow up logs"
for log_id, log in r.json().iteritems():
    last_log_line = log_id
    print log


r = requests.get('%s/pipeline/%s/job/%s' % (base_url, pipeline_id, job_id),
                  cookies=c)
assert "output1.txt" in os.listdir(r.json()[unicode(job_id)][1])
