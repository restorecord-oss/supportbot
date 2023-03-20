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
import easyocr
import random
from PIL import Image
import requests
import nltk
from nltk.corpus import words
from spellchecker import SpellChecker
spell = SpellChecker()

nltk.download('words')
word_list = words.words()
additional_words = ['redirecturi', 'oauth2', 'oauth']
word_list.extend(additional_words)

reader = easyocr.Reader(['en'], gpu=False) # this needs to run only once to load the model into memory

botToken = "MTA4NDQ1NzIzMDMzOTk0ODU4NQ.GAdGWr.2yYpdECuGb3JIfZlMpQOKD9WsvhtW2kbTKkMy8"
openai.api_key = "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"
 
guild_id = 1082007340473127102
category_id = 1086317967358312530

mongoClient = pymongo.MongoClient("mongodb://192.168.178.144:27017/")
mydb = mongoClient["RestoreCordSupport"]
col_Messages = mydb["Messages"]
col_dataset = mydb["Dataset"]
col_conversations = mydb["Conversations"]
col_chats = mydb["Chats"]

client = commands.Bot(intents=discord.Intents.all())

@client.event
async def on_ready():
    print('Logged in as {0.user}'.format(client))
    await client.change_presence(activity=discord.Game(name="[BETA] 24/7 Support!"))
    client.add_view(welcome())

@client.event
async def on_message(message):
    if message.author == client.user: # Ignore messages sent by the bot
        return
    
    user_id = message.author.id
    user_name = message.author.name
    user_nametag = message.author
    message_content = message.content
    attachment_url = None
    image_phrase = []
    
    if message.content.startswith('!close'):
        if isinstance(message.channel, discord.DMChannel):
            if(col_conversations.find_one({"user_id" : user_id})):
                await DeleteConversation(user_id)
                embed = discord.Embed(title='Conversation has been closed!', description="If you are experiencing any issues or got any questions feel free to dm me again!", color=0xf04747)
            else: 
                embed = discord.Embed(title='Conversation already closed!', description="Please start a new conversation by chatting with me!", color=0xf04747)

            embed.set_footer(text='Partially powered by OpenAI', icon_url='https://cdn.restorecord.com/logo.png')
            await message.channel.send(embed=embed)

        else:
            doc = col_conversations.find_one({"channel_id" : message.channel.id})
            if(doc["channel_id"]):
                await DeleteConversation(doc["user_id"])
                embed = discord.Embed(title='Conversation has been closed!', description="If you are experiencing any issues or got any questions feel free to dm me again!", color=0xf04747)

            embed.set_footer(text='Partially powered by OpenAI', icon_url='https://cdn.restorecord.com/logo.png')
            user = await client.fetch_user(doc["user_id"])
            await user.send(embed=embed)
            
    elif message.content.startswith("!toggle"):
        doc= None
        if isinstance(message.channel, discord.DMChannel): #DMS
            ToggleAssistant(message.user.id)
        else: #guild channel
            doc = col_conversations.find_one({"channel_id":message.channel.id})
            user = await client.fetch_user(doc["user_id"])

            if doc["AISupport"]:
                col_conversations.update_one({ "channel_id": message.channel.id }, { "$set": { "AISupport": False } })
                title='AI Support has been disabled!'; description="The admins have disabled AI support! This usually means that they are about to contact you."; color=0xf04747
            else:
                col_conversations.update_one({ "channel_id": message.channel.id }, { "$set": { "AISupport": True } })
                title='AI Support has been enabled!'; description="The admins have enabled AI support! Welcome back my friend!."; color=0x2ecc70
        
        embed = discord.Embed(title=title, description=description, color=color)
        await user.send(embed=embed)
        if doc:
            channel = await client.fetch_channel(doc["channel_id"])
            await channel.send(embed=embed)

    elif isinstance(message.channel, discord.DMChannel) and message.author != client.user and not message.content.startswith("!"): # The bot received a DM from a user other than itself
        
        aaa = col_conversations.count_documents({"user_id" : user_id})
        print("[?] Conversation counter:", aaa)
        print(f'[?] Received DM from {user_nametag}: {message_content}')
        
        if aaa < 1:
            await CreateConversation(user_name, user_id)
        else:

            
            if(col_conversations.find_one({"user_id": user_id}))["AISupport"]:
                if message.attachments:
                    await message.add_reaction('🕐')
                    attachment=message.attachments[0]
                    attachment_url=attachment.url
                    image_phrase = await OCR(attachment_url)
                    print(client)
                    await message.remove_reaction('🕐', client.user)

                await message.add_reaction('👀')
                await AddMessage(user_id, message_content, role = "user", attachment=attachment_url)
                async with message.channel.typing():
                    solution = await findSolution(message_content, image_phrase)
                    if solution:
                        await AddMessage(user_id, message =  await openaiChatCompletion(solution, str(message.author.name), user_id))

    elif isinstance(message.channel, discord.TextChannel) and message.guild.id == guild_id and message.channel.category_id == category_id:
        user_id = col_conversations.find_one({"channel_id" : message.channel.id})["user_id"]
        if message.attachments:
                attachment=message.attachments[0]
                attachment_url=attachment.url
        await AddMessage( message.author.id, message_content, role = "staff", attachment= attachment_url, channel_id= message.channel.id)
        if not message.attachments:
            await message.delete()

async def findSolution(phrase, image_phrase = []):
    doc_count = {}
    phrase = phrase.lower().translate(str.maketrans('', '', string.punctuation)).split() # split words from message
    phrase = phrase + image_phrase # Combine words from image and message
    #phrase = [word for word in phrase if word in word_list] # check if the word is in the english dictionairy
    print ("Phrase after clearing: ", phrase)

    for word in phrase:
        matches = col_dataset.count_documents({'keyword': {'$regex': f'.*{word}.*'}})
        for doc in col_dataset.find({'keyword': {'$regex': f'.*{word}.*'}}, {'_id': 1}):
            if str(doc['_id']) in doc_count:
                doc_count[str(doc['_id'])] += matches
            else:
                doc_count[str(doc['_id'])] = matches

    if not doc_count:
        solutionID = None
        solutionPhrase = None
    else:
        solutionID = max(doc_count, key=doc_count.get)
        solutionPhrase = col_dataset.find_one({"_id": ObjectId(solutionID)})["solution"]
        
    return solutionPhrase

async def AddMessage(user_id, message, role = "support", type = "message", color = None, username = None, attachment = None, channel_id = None, title= None) : # Send a message to booth user and channel
    print(f"[?] AddMessage({user_id}, {message}, {role})")
    openai_logo = "https://cdn.discordapp.com/attachments/1084460022060298240/1086807072777179266/unnamed.jpg"
    sendUser = False
    sendChannel = False
    embed = None
    user = await client.fetch_user(user_id)
    avatar = user.avatar
    if avatar == None: avatar = "https://cdn.discordapp.com/embed/avatars/1.png" 

    if type == "message":
        if role == "support":
            if color == None: color=0x5865f2
            channel_id = col_conversations.find_one({"user_id": user_id})["channel_id"]
            embed = discord.Embed(description=message, color = color)
            embed.set_footer(text='Partially powered by OpenAI',)
            embed.set_author(name="Smart Assistant [BETA]", icon_url= "https://cdn.restorecord.com/logo.png")
            embed.set_footer(text='Partially powered by OpenAI', icon_url=openai_logo)
            sendUser = True; sendChannel = True

        elif role == "user":
            channel_id = col_conversations.find_one({"user_id": user_id})["channel_id"]
            user = await client.fetch_user(user_id)
            if color == None: color=0xf1c40f
            sendChannel = True

        elif role == "staff":
            if color == None: color=0x2ecc70
            sendUser = True; sendChannel = True

        elif role == "private":
            if color == None: color=0xeb459e
            sendChannel = True

        elif role == "custom":
            channel_id = col_conversations.find_one({"user_id": user_id})["channel_id"]
            embed = discord.Embed(title=f'**{title}**', description=message, color = color)
            sendUser = True; sendChannel = True

    if type == "welcome":
        if role == "support":
            if color == None: color=0x43b581
            embed = discord.Embed(title='**A smart conversation has been created!**', description=message, color = color)
            embed.set_footer(text='Partially powered by OpenAI', icon_url=openai_logo)
            channel_id = col_conversations.find_one({"user_id": user_id})["channel_id"]
            channel = await client.fetch_channel(channel_id)
            await channel.send(embed=embed)
            await user.send(embed=embed, view=welcome())
            return

    if type == "success": ## with buttons
        if role == "support":
            if color == None: color = 0x43b581
            embed = discord.Embed(title='Smart Assistant [BETA]', description=message, color = color)
            embed.set_footer(text='Partially powered by OpenAI', icon_url=openai_logo)
            sendUser = True; sendChannel = True
    
    channel = await client.fetch_channel(channel_id)

    if embed == None:
        embed = discord.Embed(description=message, color = color)
        embed.set_author(name=user.name, icon_url=avatar)
    if attachment != None: embed.set_image(url=attachment)

    if sendUser: await user.send(embed=embed)
    if sendChannel: await channel.send(embed=embed)

async def Situation(situation, user_id): # Situations with a set script such as "paying with paypal" ,"talking to staff" or "issue has been solved"
    if situation == "paymentPaypal":
        print("[?] Situation: ", situation)
    
    if situation == "contactTeam":
        print("[?] Situation: ", situation)

    if situation == "reportBug":
        print("[?] Situation: ", situation)

    if situation == "botDisabled":
        print("[?] Situation: ", situation)

    if situation == "issueResolved":
        print("[?] Situation: ", situation)
        
async def CreateConversation(username, user_id):
    print(f"[?] CreateConversation({username}, {user_id})" )
    guild = client.get_guild(guild_id)

    category = discord.utils.get(guild.categories, name="ai support") # check if catgory exists, if not create one
    if category is None:
        category = await guild.create_category("ai support")

    await guild.create_text_channel(name=str(username), category = category, topic = user_id)

    col_conversations.insert_one({"user_name": str(username), "user_id": user_id, "guild_id": guild_id, "category_id": category_id, "topic": user_id, "channel_id": await find_channel_with_topic(user_id), "onGoing": True, "AISupport": True}) # insert to database
    col_chats.insert_one({"user_id" : user_id, "stage" : 1})

    await AddMessage(user_id, type="welcome", message='\n**Hello there!** \nPlease ask me any question related to RestoreCord such as posting an error messages or screenshots of the issues you are experience! \n I\'ll try my best to solve them as fast as possible.\n\n**If you want to talk a human then click the "Talk to Humans" button!**')

async def DeleteConversation(user_id):
    print("[?] Deleting Conversation of:", user_id)
    doc = col_conversations.find_one({"user_id" : user_id})

    col_conversations.delete_one({"user_id" : user_id})
    col_chats.delete_one({"user_id" : user_id})
    guild = client.get_guild(guild_id)
    channel = guild.get_channel(doc["channel_id"])
    await channel.delete()

async def openaiChatCompletion(query, username, userid):
    print("[?] openaiChatCompletion: ", query)
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

class welcome(discord.ui.View): 
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Talk to Humans!", style=discord.ButtonStyle.primary, emoji="🧑‍💻", custom_id="talk_human") 
    async def button_callback1(self, button, interaction):
        user_id = interaction.user.id
        if(col_conversations.find_one({"user_id" : user_id})):
            channel = await find_channel_with_topic(user_id)
            channel = await client.fetch_channel(channel)
            embed = discord.Embed(title='Humans have been invited to this conversation!', description="The Support Team will have a look and will come back to you as soon as possible!", color=0x9cdcfe)
            embed.set_footer(text='Partially powered by OpenAI', icon_url='https://cdn.restorecord.com/logo.png')

            doc = col_conversations.find_one({"user_id" : user_id})
            await channel.send(f"‎\n\n**|   <@&1082054289951825930> User is requesting help!**\n\n‎")

        else:
            embed = discord.Embed(title='Conversation already closed!', description="Please start a new conversation by chatting with me!", color=0xf04747)
            embed.set_footer(text='Partially powered by OpenAI', icon_url='https://cdn.restorecord.com/logo.png')

        await interaction.response.send_message(embed=embed)
        button.disabled = True
        await interaction.message.edit(view=self)


    @discord.ui.button(label="Close Conversation!", style=discord.ButtonStyle.danger, emoji="⛔", custom_id="close_conversation") 
    async def button_callback2(self, button, interaction):
        if(col_conversations.find_one({"user_id" : interaction.user.id})):
            embed = discord.Embed(title='Conversation has been closed!', description="If you are experiencing any issues or got any questions feel free to dm me again!", color=0xf04747)
            await DeleteConversation(user_id = interaction.user.id)    
        else:
            embed = discord.Embed(title='Conversation already closed!', description="Please start a new conversation by chatting with me!", color=0xf04747)
        
        embed.set_footer(text='Partially powered by OpenAI', icon_url='https://cdn.restorecord.com/logo.png')
        await interaction.response.send_message(embed=embed)
        button.disabled = True
        await interaction.message.edit(view=self)  
    
    @discord.ui.button(label="Toggle Smart Assistant!", style=discord.ButtonStyle.green, emoji="🤖", custom_id="toggle_assistant") 
    async def button_callback3(self, button, interaction):
        await ToggleAssistant(interaction.user.id)
        await interaction.response.defer()


async def ToggleAssistant(user_id):
    print("[?] Toggling Smart Assistant for: ",user_id)
    user = await client.fetch_user(user_id)
    if( col_conversations.count_documents({"user_id":user_id}) == 0):
        title = 'Conversation already closed!'; description= "Please start a new conversation by talking to me!"; color=0xf04747
    else:
        doc = col_conversations.find_one({"user_id":user_id})

    if doc["AISupport"]:
        col_conversations.update_one({ "user_id": user_id}, { "$set": { "AISupport": False } })
        title='AI Support has been disabled!'; description="Smart Assistant has been disabled, i will no longer read your messages and suggest solutions."; color=0xf04747
    else:
        col_conversations.update_one({ "user_id": user_id}, { "$set": { "AISupport": True } })
        title='AI Support has been enabled!'; description="Smart ASsistant has been re-enabled, i will understand your messages and try to solve them."; color=0x2ecc70
    await AddMessage(user_id, message=description, color=color, title=title, role="custom")

async def find_channel_with_topic(topic_content):
    await client.wait_until_ready()

    guild = client.get_guild(guild_id)

    for channel in guild.channels:
        if isinstance(channel, discord.TextChannel) and channel.topic is not None and str(topic_content) in channel.topic:
            return channel.id
    return None

async def OCR(image_url):
    print ("[?] Reading text from image", image_url)
    image = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(16))
    response = requests.get(image_url)
    image_phrase = None

    with open(image, 'wb') as f:
        f.write(response.content)

    text = reader.readtext(image, detail = 0)

    image_phrase = ' '.join(text)
    image_phrase = image_phrase.lower().translate(str.maketrans('', '', string.punctuation)).split()

    os.remove(image)

    print(f"[?] Text from Image: {image_phrase}")
    return image_phrase

client.run(str(botToken))