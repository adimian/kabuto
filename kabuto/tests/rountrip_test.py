'''
This test relies on the fact that both kabuto and ammonite services are running standalone
'''
import requests
import os
from kabuto.tests import sample_dockerfile
import time

ROOT_DIR = os.path.abspath(os.path.dirname(os.path.abspath(__file__)))
data = {'command': 'cp /inbox/file1.txt /outbox/output1.txt'}
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

r = requests.get('%s/pipeline/%s/job/%s' % (base_url, pipeline_id, job_id),
                  cookies=c)

# Poll the execution for it's state to continue, not implemented yet
# so doing a dirty sleep
# r = requests.get('%s/execution/%s' % (base_url, eid),
#                   cookies=c)
# while not r.json()[unicode(eid)] == "done":
#     time.sleep(1)
time.sleep(1)
assert "output1.txt" in os.listdir(r.json()[unicode(job_id)][1])