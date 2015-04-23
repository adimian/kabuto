'''
This test relies on the fact that both kabuto and ammonite
services are running standalone
'''
import requests
import os
import time
import argparse

parser = argparse.ArgumentParser()
group = parser.add_mutually_exclusive_group()
group.add_argument('--normal', action='store_true')
group.add_argument('--memory', action='store_true')
group.add_argument('--cpu', action='store_true')
group.add_argument('--big_file', action='store_true')
args = parser.parse_args()

ROOT_DIR = os.path.abspath(os.path.dirname(os.path.abspath(__file__)))
base_url = "http://127.0.0.1:5000"


def do_a_barrel_roll(data, files, base_url, dockerfile, dockername, file_name):
    r = requests.post('%s/login' % base_url, data={'login': 'maarten',
                                                   'password': 'test'})
    assert r.status_code == 200
    c = r.cookies

    r = requests.post('%s/image' % base_url,
                      data={'dockerfile': dockerfile,
                            'name': dockername},
                      cookies=c)

    image_id = r.json()['id']
    print("created image")

    r = requests.post('%s/pipeline' % base_url,
                      data={'name': 'my first pipeline'},
                      cookies=c)
    pipeline_id = r.json()['id']
    print("created pipeline")

    data['image_id'] = image_id
    r = requests.post('%s/pipeline/%s/job' % (base_url, pipeline_id),
                      data=data,
                      files=files,
                      cookies=c)

    job_id = r.json()['id']
    print("created job")

    r = requests.post('%s/pipeline/%s/submit' % (base_url, pipeline_id),
                      cookies=c)
    print("submitted job with following executions:")
    for eid, state in r.json().items():
        print("id: %s - state(%s)" % (eid, state))

    r = requests.get('%s/execution/%s/logs' % (base_url, job_id),
                     cookies=c)
    print("Initial logs")
    last_log_line = -1
    for log_id, log in r.json().items():
        last_log_line = log_id
        print(log)

    def poll_for_state():
        url = "%s/pipeline/%s/job/%s" % (base_url, pipeline_id, job_id)
        r = requests.get(url, cookies=c)
        return r.json()[str(job_id)]["state"]

    state = poll_for_state()
    while not state == "done":
        print("state is %s" % state)
        print("polling...")
        state = poll_for_state()
        time.sleep(1)

    r = requests.get('%s/execution/%s/logs/%s' % (base_url,
                                                  job_id,
                                                  last_log_line),
                     cookies=c)
    print("Follow up logs")
    for log_id, log in r.json().items():
        last_log_line = log_id
        print(log)

    r = requests.get('%s/pipeline/%s/job/%s' % (base_url, pipeline_id, job_id),
                     cookies=c)
    assert file_name in os.listdir(r.json()[str(job_id)]["results_path"])

sample_dockerfile = '''FROM busybox
CMD ["echo", "hello world"]
'''

memory_docker_file = '''FROM phusion/baseimage:0.9.16
CMD ["echo", "hello world"]
'''

big_file_docker_file = '''FROM phusion/baseimage:0.9.16
RUN apt-get update && apt-get install python python-dev -y
CMD ["echo", "hello world"]
'''

if args.normal:
    data = {'command': ['cp /inbox/file1.txt /outbox/output1.txt']}
    files = [("attachments", open(os.path.join(ROOT_DIR,
                                               "data", "file1.txt"), "rb")),
             ("attachments", open(os.path.join(ROOT_DIR,
                                               "data", "file2.txt"), "rb"))]
    do_a_barrel_roll(data, files, base_url, sample_dockerfile,
                     'hellozeworld', 'output1.txt')
elif args.cpu:
    data = {'command': ["timeout 30 yes && echo done > /outbox/done.txt"]}
    files = []
    do_a_barrel_roll(data, files, base_url, memory_docker_file,
                     'hellozeworldmem', 'done.txt')
elif args.big_file or args.memory:
    data = {'command': ["python /inbox/big_file_creator.py"]}
    files = [("attachments", open(os.path.join(ROOT_DIR, "data",
                                               "big_file_creator.py"), "rb"))]
    do_a_barrel_roll(data, files, base_url, big_file_docker_file,
                     'hellozeworldbf', 'big_file.txt')
