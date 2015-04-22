from contextlib import contextmanager

import pika

@contextmanager
def open_channel(host):
    connection = pika.BlockingConnection(pika.ConnectionParameters(
        host=host))
    channel = connection.channel()
    yield channel
    connection.close()

def put_in_message_queue(queue, message):
    host = app.config['AMQP_HOSTNAME']
    with open_channel(host) as channel:
        channel.queue_declare(queue=queue, durable=True)
        properties = pika.BasicProperties(delivery_mode=2,)
        channel.basic_publish(exchange='',
                              routing_key=queue,
                              body=message,
                              properties=properties)

def publish_job(message):
    put_in_message_queue(queue='jobs', message=message)