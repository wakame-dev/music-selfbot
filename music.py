import asyncio
import random
from concurrent.futures import ThreadPoolExecutor
import discord
from yt_dlp import YoutubeDL
from dotenv import load_dotenv
import os

load_dotenv()  # .env ファイルの読み込み

PREFIX = "-"
TOKEN = os.getenv("TOKEN")  # .env からトークンを取得

client = discord.Client()

ydl = YoutubeDL({
    "quiet": True,
    "format": "bestaudio/best",
    "noplaylist": True,
    "cookiefile": "./cookie.txt",
})

queue = asyncio.Queue()
looping = False

def _isPlayList(url: str, locale: str = "ja") -> list[dict] | bool:
    try:
        lang = "ja" if locale == "ja" else locale
        ydlOpts = {
            "quiet": True,
            "extract_flat": True,
            "cookiefile": "./cookie.txt",
            "extractor_args": {"youtube": {"lang": [lang]}},
        }
        with YoutubeDL(ydlOpts) as ydl:
            info = ydl.sanitize_info(ydl.extract_info(url, download=False))
        return info["entries"] if "entries" in info else [info]
    except Exception:
        return False

async def isPlayList(url: str) -> list[str] | bool:
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as executor:
        return await loop.run_in_executor(executor, _isPlayList, url)

def fetchVideo(url: str):
    return ydl.sanitize_info(ydl.extract_info(url, download=False))

async def playAudio(guild: discord.Guild):
    if queue.qsize() <= 0:
        if guild.voice_client:
            await guild.voice_client.disconnect()
        return
    url, ctx, volume = await queue.get()
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as executor:
        info = await loop.run_in_executor(executor, fetchVideo, url)
    options = {
        "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
        "options": "-vn -bufsize 64k -analyzeduration 2147483647 -probesize 2147483647",
    }
    source = discord.PCMVolumeTransformer(
        discord.FFmpegPCMAudio(info.get("url"), **options), volume
    )
    voiceClient = ctx.guild.voice_client

    def after(e: Exception):
        if voiceClient.is_playing():
            voiceClient.stop()
        if voiceClient.is_connected():
            task = asyncio.run_coroutine_threadsafe(playAudio(guild), loop=loop)
            if not looping:
                task.cancel()

    voiceClient.play(source, after=after)

@client.event
async def on_message(message: discord.Message):
    global looping
    if message.author == client.user:
        return

    if message.content.startswith(f"{PREFIX}play"):
        url = message.content.split(" ")[1]
        volume = float(message.content.split(" ")[2]) if len(message.content.split(" ")) > 2 else 0.5
        if not message.author.voice:
            await message.add_reaction("❌ ")
            return
        for info in await isPlayList(url):
            await queue.put((info["webpage_url"], message, volume))
        if message.guild.voice_client:
            await message.add_reaction("👍")
            return
        await message.author.voice.channel.connect()
        await playAudio(message.guild)
    
    elif message.content.startswith(f"{PREFIX}splay"):
        url = message.content.split(" ")[1]
        volume = float(message.content.split(" ")[2]) if len(message.content.split(" ")) > 2 else 0.5
        if not message.author.voice:
            await message.add_reaction("❌ ")
            return
        shuffledData = await isPlayList(url)
        random.shuffle(shuffledData)
        for info in shuffledData:
            await queue.put((info["webpage_url"], message, volume))
        if message.guild.voice_client:
            await message.add_reaction("👍")
            return
        await message.author.voice.channel.connect()
        await playAudio(message.guild)

    elif message.content.startswith(f"{PREFIX}skip"):
        voiceClient = message.guild.voice_client
        await voiceClient.stop()
        await message.add_reaction("👍")

    elif message.content.startswith(f"{PREFIX}stop"):
        voiceClient = message.guild.voice_client
        await voiceClient.disconnect()
        await message.add_reaction("👍")

    elif message.content.startswith(f"{PREFIX}pause"):
        voiceClient = message.guild.voice_client
        voiceClient.pause()
        await message.add_reaction("👍")

    elif message.content.startswith(f"{PREFIX}resume"):
        voiceClient = message.guild.voice_client
        voiceClient.resume()
        await message.add_reaction("👍")

    elif message.content.startswith(f"{PREFIX}loop"):
        looping = not looping
        status = "enabled" if looping else "disabled"
        await message.channel.send(f"Looping is now {status}.")

    elif message.content.startswith(f"{PREFIX}help"):
        await message.channel.send(
            f"```{PREFIX}play <URL> [volume] - Play audio\n{PREFIX}splay <URL> [volume] - Shuffle play\n{PREFIX}skip - Skip the song\n{PREFIX}stop - Stop audio\n{PREFIX}pause - Pause\n{PREFIX}resume - Resume\n{PREFIX}loop - Toggle looping```"
        )

client.run(TOKEN)
