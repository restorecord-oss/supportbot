import openai
import json
import os
import discord
from discord.ext import commands
from discord import ui
import pymongo
import asyncio
import re
import string
from bson.objectid import ObjectId
import time
import pytesseract
import random
from PIL import Image
import requests
import nltk
from nltk.corpus import words
from spellchecker import SpellChecker
import buttons


def openaiChatCompletion(query, username, userid):
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        max_tokens=150,
        messages=[
        {"role": "system", "content": f'You are a intelligent personal assistant. You are only allowed to write short and easy to understand solutions. Rewrite the text given to you in a prmoising way. You may use Discord Markdown to format your answers.'},
        {"role": "assistant", "content": query},
        ]
    )
    response = json.loads(str(response))
    
    answer = response["choices"][0]["message"]["content"]
    price = response["usage"]["total_tokens"]

    doc = {"username": username, "userid": userid, "question": query, "answer": answer, "cost": price, "erased": False}
    col_Messages.insert_one(doc) # insert to database
    return answer


async def find_channel_with_topic(topic_content):
    await client.wait_until_ready()

    guild = client.get_guild(guild_id)

    for channel in guild.channels:
        if isinstance(channel, discord.TextChannel) and channel.topic is not None and str(topic_content) in channel.topic:
            return channel.id
    return None

def OCR(image_url):
    print ("[?] Reading text from image", image_url)
    filename = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
    response = requests.get(image_url)
    image_phrase = None

    with open('image.jpg', 'wb') as f:
        f.write(response.content)

    img = Image.open('image.jpg')
    text = pytesseract.image_to_string(img)

    image_phrase = text.lower().translate(str.maketrans('', '', string.punctuation))
    image_phrase = image_phrase.split()

    os.remove('image.jpg')

    print(f"[?] Text from Image: {image_phrase}")
    return image_phrase