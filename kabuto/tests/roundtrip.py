from requests import Session
import time

base_url = "http://localhost:5000"
dockerfile = '''FROM phusion/baseimage:0.9.16
CMD ["echo", "hello world"]
'''
s = Session()
r = s.post('%s/login' % base_url, data={'login': 'me',
                                        'password': 'SecreT'})

r = s.post('%s/image' % base_url,
           data={'dockerfile': dockerfile,
                 'name': "test"})
build_id = r.json()['build_id']


def wait_for_image():
    r = s.get('%s/image/build/%s' % (base_url, build_id))
    build_data = r.json()
    return build_data

build_data = wait_for_image()
print(build_data)
state = build_data['state']
while state == 'PENDING':
    print("state is pending, waiting for 1s")
    time.sleep(1)
    build_data = wait_for_image()
    state = build_data['state']

image_id = build_data['id']
print(build_data['output'])
print("created image")

r = s.post('%s/pipeline' % base_url, data={'name': 'my first pipeline'})
pipeline_id = r.json()['id']
print("created pipeline")
print(pipeline_id)

data = {'command': ['ls -al']}
data['image_id'] = image_id
r = s.post('%s/pipeline/%s/job' % (base_url, pipeline_id), data=data)

job_id = r.json()['id']
print("created job")

r = s.post('%s/pipeline/%s/submit' % (base_url, pipeline_id))
print("submitted job with following executions:")
for eid, state in r.json().items():
    print("id: %s - state(%s)" % (eid, state))

r = s.get('%s/execution/%s/logs' % (base_url, job_id))
print("Initial logs")
last_log_line = -1
for line in r.json():
    print(line)


def poll_for_state():
    url = "%s/pipeline/%s/job/%s" % (base_url, pipeline_id, job_id)
    r = s.get(url)
    return r.json()[str(job_id)]["state"]

state = poll_for_state()
while not state == "done":
    print("state is %s" % state)
    print("polling...")
    state = poll_for_state()
    time.sleep(1)

r = s.get('%s/execution/%s/logs/%s' % (base_url,
                                       job_id,
                                       0),
                 cookies=c)
print("Follow up logs")
for line in r.json():
    print(line)


