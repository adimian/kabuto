from contextlib import contextmanager

import pika


@contextmanager
def open_channel(config):
    login = config['AMQP_USER']
    password = config['AMQP_PASSWORD']
    if login and password:
        credentials = pika.PlainCredentials(login, password)
    else:
        credentials = None

    host = config['AMQP_HOSTNAME']
    connection = pika.BlockingConnection(
        pika.ConnectionParameters(
            host=host,
            credentials=credentials,
        ))
    channel = connection.channel()
    yield channel
    connection.close()

def put_in_message_queue(queue, message, config):
    with open_channel(config) as channel:
        channel.queue_declare(queue=queue, durable=True)
        properties = pika.BasicProperties(delivery_mode=2,)
        channel.basic_publish(exchange='',
                              routing_key=queue,
                              body=message,
                              properties=properties)

def publish_job(message, config):
    put_in_message_queue('jobs', message, config)
