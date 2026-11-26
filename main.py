import asyncio
import os
import logging
from datetime import datetime

import httpx
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError


# ==============================
# Logging
# ==============================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

logging.getLogger("httpx").setLevel(logging.WARNING)


# ==============================
# Configuration
# ==============================

BASE = os.getenv(
    "WP_REST_BASE",
    "https://brokshield.com/wp-json/bssa/v1/"
).rstrip("/") + "/"

START = datetime.fromisoformat(
    os.environ["START_FROM_UTC"].replace("Z", "+00:00")
)

if START.tzinfo is None:
    raise ValueError("START_FROM_UTC requires timezone")

POLL = max(
    15,
    int(os.getenv("POLL_SECONDS", "20"))
)


# ==============================
# Main Listener
# ==============================

async def main():

    logging.info("BrokShield Telegram Listener starting")
    logging.info("Polling interval: %s seconds", POLL)
    logging.info("Start date: %s", START.isoformat())

    client = TelegramClient(
        StringSession(os.environ["TG_SESSION"]),
        int(os.environ["TG_API_ID"]),
        os.environ["TG_API_HASH"]
    )

    try:

        await client.connect()

        if not await client.is_user_authorized():
            raise RuntimeError(
                "Telegram session not authorized"
            )

        logging.info("Telegram authorization successful")

        cursors = {}

        async with httpx.AsyncClient(
            base_url=BASE,
            headers={
                "X-BSSA-Key": os.environ["WP_LISTENER_KEY"],
                "Cache-Control": "no-cache, no-store",
                "Pragma": "no-cache"
            },
            timeout=40,
            follow_redirects=False
        ) as http:

            while True:

                try:

                    response = await http.get(
                        "config",
                        params={
                            "_t": int(datetime.now().timestamp())
                        }
                    )

                    response.raise_for_status()
                    config = response.json()

                    if not config.get("enabled"):

                        logging.info(
                            "Publishing disabled in WordPress"
                        )

                        await asyncio.sleep(POLL)
                        continue

                    sources = config.get("sources", [])

                    logging.info(
                        "Publishing enabled | Sources: %s",
                        len(sources)
                    )

                    for rule in sources:

                        name = rule["channel"]

                        try:

                            logging.info(
                                "Checking source: %s",
                                name
                            )

                            peer = await client.get_entity(
                                "@" + name.lstrip("@")
                            )

                            if name not in cursors:

                                old = await client.get_messages(
                                    peer,
                                    limit=1,
                                    offset_date=START
                                )

                                cursors[name] = (
                                    old[0].id if old else 0
                                )

                                logging.info(
                                    "Source initialized: %s",
                                    name
                                )

                            async for m in client.iter_messages(
                                peer,
                                min_id=cursors[name],
                                reverse=True
                            ):

                                if m.date >= START and m.message:

                                    payload = {
                                        "source": name,
                                        "id": m.id,
                                        "reply": m.reply_to_msg_id or 0,
                                        "text": m.message,
                                        "date": int(
                                            m.date.timestamp()
                                        )
                                    }

                                    r = await http.post(
                                        "message",
                                        json=payload
                                    )

                                    r.raise_for_status()

                                    result = r.json()

                                    if result.get("ignored"):

                                        logging.info(
                                            "Message ignored | %s | ID: %s",
                                            name,
                                            m.id
                                        )

                                    elif result.get("ok"):

                                        logging.info(
                                            "Message processed | %s | ID: %s",
                                            name,
                                            m.id
                                        )

                                    else:

                                        raise RuntimeError(
                                            "Unexpected WordPress response"
                                        )

                                cursors[name] = m.id

                        except FloodWaitError as e:

                            logging.warning(
                                "Telegram rate limit: %s seconds",
                                e.seconds
                            )

                            await asyncio.sleep(
                                e.seconds + 1
                            )

                        except httpx.HTTPStatusError as e:

                            logging.error(
                                "MESSAGE API ERROR | Source: %s | HTTP: %s",
                                name,
                                e.response.status_code
                            )

                        except httpx.RequestError as e:

                            logging.error(
                                "WordPress connection error | Source: %s | Type: %s",
                                name,
                                type(e).__name__
                            )

                        except Exception as e:

                            logging.error(
                                "Source failed | %s | Error: %s",
                                name,
                                type(e).__name__
                            )

                except httpx.HTTPStatusError as e:

                    logging.error(
                        "CONFIG API ERROR | HTTP: %s",
                        e.response.status_code
                    )

                except httpx.RequestError as e:

                    logging.error(
                        "CONFIG CONNECTION ERROR | %s",
                        type(e).__name__
                    )

                except Exception as e:

                    logging.error(
                        "CONFIG ERROR | %s",
                        type(e).__name__
                    )

                await asyncio.sleep(POLL)

    finally:

        await client.disconnect()

        logging.info("Telegram Listener disconnected")


if __name__ == "__main__":

    asyncio.run(main())
