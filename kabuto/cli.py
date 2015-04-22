#! /usr/bin/env python3

from argparse import ArgumentParser

from utils import open_channel
from config import Config


INFO_TPL = '''Info for "%s" queue:
Number of consumers: %s
Number of messages: %s
'''

# Action define a cli action
class Action:
    actions = {}

    def __init__(self, *required , optional=None):
        self.required = required
        self.optional = optional

    def __call__(self, fn):
        self.name = fn.__name__
        self.actions[self.name] = self
        self.fn = fn
        self.help = fn.__doc__
        return fn

    @classmethod
    def get(cls, name, default=None):
        return cls.actions.get(name, default)

    @classmethod
    def all(cls):
        return sorted(cls.actions.keys())

    def launch(self, *args, **kwars):
        if len(args) < len(self.required):
            print('Error: %s need at least %s arguments' % (
                self.name, len(self.required)))
            return
        return self.fn(*args, **kwars)

@Action(optional='action')
def help(action_name=None):
    'This help'

    if action_name and Action.get(action_name):
        actions = [action_name]
    else:
        actions = Action.all()
    for action_name in actions:
        action = Action.get(action_name)
        print('   %s: %s' % (action_name, action.help))


@Action('queue name')
def delete(queue_name):
    'Delete the given queue'
    with open_channel(Config.AMQP_HOSTNAME) as channel:
        channel.queue_delete(queue_name)

@Action('queue name')
def purge(queue_name):
    'Purge the given queue'
    with open_channel(Config.AMQP_HOSTNAME) as channel:
        channel.queue_purge(queue_name)

@Action('queue name')
def declare(queue_name):
    'Declare the given queue'
    with open_channel(Config.AMQP_HOSTNAME) as channel:
        channel.queue_declare(queue=queue_name, durable=True)

@Action('queue name')
def info(queue_name):
    'Get info for the given queue'
    with open_channel(Config.AMQP_HOSTNAME) as channel:
        info = channel.queue_declare(
            queue=queue_name,
            passive=True,
        )
    print(INFO_TPL % (
        queue_name,
        info.method.consumer_count,
        info.method.message_count)
    )

if __name__ == '__main__':
    action_list = ', '.join(Action.all())
    parser = ArgumentParser(
        description='Kabuto command line utility',
    )
    parser.add_argument(
        'action', nargs='+', help='One of: %s' % action_list)
    args = parser.parse_args()

    action_name = args.action[0]
    action = Action.get(action_name)
    if action is None:
        parser.error('Unknown action "%s"' % action_name)
    action.launch(*args.action[1:])
