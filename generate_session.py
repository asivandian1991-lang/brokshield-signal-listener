from getpass import getpass
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
api_id=int(input('Telegram API ID: '))
api_hash=getpass('Telegram API Hash: ')
with TelegramClient(StringSession(),api_id,api_hash) as client:
    print('PRIVATE SESSION (store only in Northflank secrets):')
    print(client.session.save())
