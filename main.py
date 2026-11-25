import asyncio, os, logging
from datetime import datetime, timezone
import httpx
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logging.getLogger('httpx').setLevel(logging.WARNING)
BASE = os.getenv('WP_REST_BASE', 'https://brokshield.com/wp-json/bssa/v1/').rstrip('/')+'/'
START = datetime.fromisoformat(os.environ['START_FROM_UTC'].replace('Z','+00:00'))
if START.tzinfo is None: raise ValueError('START_FROM_UTC requires timezone')
POLL = max(15, int(os.getenv('POLL_SECONDS','20')))

async def main():
    client = TelegramClient(StringSession(os.environ['TG_SESSION']), int(os.environ['TG_API_ID']), os.environ['TG_API_HASH'])
    await client.connect()
    try:
        if not await client.is_user_authorized(): raise RuntimeError('Telegram session not authorized')
        cursors = {}
        async with httpx.AsyncClient(base_url=BASE, headers={'X-BSSA-Key':os.environ['WP_LISTENER_KEY']}, timeout=40, follow_redirects=False) as http:
            while True:
                try:
                    response=await http.get('config'); response.raise_for_status(); config=response.json()
                    if config['enabled']:
                        for rule in config['sources']:
                            name=rule['channel']
                            try:
                                peer=await client.get_entity('@'+name)
                                if name not in cursors:
                                    # Find last message strictly before the configured start.
                                    old=await client.get_messages(peer,limit=1,offset_date=START)
                                    cursors[name]=old[0].id if old else 0
                                async for m in client.iter_messages(peer,min_id=cursors[name],reverse=True):
                                    if m.date >= START and m.message:
                                        r=await http.post('message',json={'source':name,'id':m.id,'reply':m.reply_to_msg_id or 0,'text':m.message,'date':int(m.date.timestamp())})
                                        r.raise_for_status()
                                        result=r.json()
                                        if not (result.get('ok') or result.get('ignored')): raise RuntimeError('Unexpected WordPress response')
                                    cursors[name]=m.id
                            except FloodWaitError as e:
                                logging.warning('Telegram rate limit: %s seconds',e.seconds); await asyncio.sleep(e.seconds+1)
                            except Exception as e:
                                logging.warning('Source %s failed: %s',name,type(e).__name__)
                    else: logging.info('Publishing disabled in WordPress')
                except Exception as e: logging.warning('Config request failed: %s',type(e).__name__)
                await asyncio.sleep(POLL)
    finally: await client.disconnect()

if __name__=='__main__': asyncio.run(main())
