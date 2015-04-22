from contextlib import contextmanager

import pika

@contextmanager
def open_channel(host):
    connection = pika.BlockingConnection(pika.ConnectionParameters(
        host=host))
    channel = connection.channel()
    yield channel
    connection.close()

def put_in_message_queue(host, queue, message):
    with open_channel(host) as channel:
        channel.queue_declare(queue=queue, durable=True)
        properties = pika.BasicProperties(delivery_mode=2,)
        channel.basic_publish(exchange='',
                              routing_key=queue,
                              body=message,
                              properties=properties)

def publish_job(host, message):
    put_in_message_queue(host, queue='jobs', message=message)
