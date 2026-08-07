import sys
from pathlib import Path
root = Path(__file__).resolve().parent
sys.path.insert(0, str(root))
from core.event_bus import Event, EventBus
from plugins.chat_ai.__init__ import ChatAIPlugin

bus = EventBus()
plugin = ChatAIPlugin()
plugin.setup(bus)
print('handlers after plugin setup', {k: len(v) for k, v in bus._handlers.items()})
received = []

def handler(event):
    print('handler called', event)
    received.append(event.payload.get('text'))

bus.subscribe('system_message', handler)
print('handlers after subscribe', {k: len(v) for k, v in bus._handlers.items()})

original_publish_sync = bus.publish_sync

def publish_sync_debug(event):
    print('publish_sync_debug event', event.name, event.payload)
    return original_publish_sync(event)

bus.publish_sync = publish_sync_debug
print('publishing user_message')
bus.publish_sync(Event(name='user_message', payload={'text': 'Qual é o seu nome?'}, source='user'))
print('received=', received)
