from telegram import Update, PhotoSize, Video
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    filters
)
from telegram import Update, PhotoSize
from telegram.ext import (
    Application,
    ContextTypes,
    MessageHandler,
    filters
)
from requests_oauthlib import OAuth1, OAuth1Session
import config
import logging
import requests 
import time
import json
import base64
import os
import sqlite3
from datetime import datetime
from datetime import timedelta


POST_TWEET_URL = "https://api.twitter.com/1.1/statuses/update.json"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

def setup_database():
    conn = sqlite3.connect('messages.db')
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_msg_id INTEGER,
        telegram_msg_content TEXT,
        twitter_msg_id INTEGER,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    conn.close()


def split_message(text, max_len):
    """Split the text into chunks of max_len, preserving line breaks and not breaking in the middle of a word."""
    lines = text.split("\n")
    chunks, chunk = [], ""

    for line in lines:
        if len(chunk) + len(line) + 1 > max_len: 
            chunks.append(chunk.strip())
            chunk = line
        else:
            chunk += "\n" + line  

        if len(chunk) > max_len:
            words = chunk.split()
            temp_chunk = ""
            for word in words:
                if len(temp_chunk) + len(word) > max_len:
                    chunks.append(temp_chunk.strip())
                    temp_chunk = word
                else:
                    if temp_chunk:
                        temp_chunk += " " + word
                    else:
                        temp_chunk = word
            chunk = temp_chunk

    if chunk:
        chunks.append(chunk.strip())

    return chunks



def get_images_id(): 
        oauth = OAuth1(config.CONSUMER_API_KEY,
        config.CONSUMER_API_KEY_SECRET,
        config.ACCESS_TOKEN,
        config.ACCESS_TOKEN_SECRET)
        
        with open("tmp_photo.jpg", "rb") as file:
                image_data = file.read()

        b64_image = base64.b64encode(image_data)
        upload_endpoint = 'https://upload.twitter.com/1.1/media/upload.json'
        headers = {'Authorization': 'application/octet-stream'}
        response = requests.post(upload_endpoint, headers=headers,
                                    data={'media_data': b64_image},
                                    auth=oauth)
        id = json.loads(response.text)['media_id']
       
        return id

def get_video_id(): 
        oauth = OAuth1(config.CONSUMER_API_KEY,
        config.CONSUMER_API_KEY_SECRET,
        config.ACCESS_TOKEN,
        config.ACCESS_TOKEN_SECRET)
        
        with open("tmp_video.mp4", "rb") as file:
                image_data = file.read()

        b64_image = base64.b64encode(image_data)
        video_filename = "tmp_video.mp4"
        total_bytes = os.path.getsize("tmp_video.mp4")
        media_id = None
        processing_info = None
        request_data = {
            'command': 'INIT',
            'media_type': 'video/mp4',
            'total_bytes': total_bytes,
            'media_category': 'tweet_video'
            }

        upload_endpoint = 'https://upload.twitter.com/1.1/media/upload.json'
        headers = {'Authorization': 'application/octet-stream'}
        response = requests.post(upload_endpoint, headers=headers,
                                    data=request_data,
                                    auth=oauth)
        media_id = response.json()['media_id']

        upload_append(video_filename, media_id, total_bytes,oauth,upload_endpoint)

        return media_id

def upload_append(video_filename, media_id, total_bytes,oauth,upload_endpoint):
     
    segment_id = 0
    bytes_sent = 0
    file = open(video_filename, 'rb')

    while bytes_sent < total_bytes:
      chunk = file.read(4*1024*1024)
      
      print('APPEND')

      request_data = {
        'command': 'APPEND',
        'media_id': media_id,
        'segment_index': segment_id
      }

      files = {
        'media':chunk
      }

      req = requests.post(url=upload_endpoint, data=request_data, files=files, auth=oauth)

      if req.status_code < 200 or req.status_code > 299:
        print(req.status_code)
        print(req.text)
        return

      segment_id = segment_id + 1
      bytes_sent = file.tell()

      print('%s of %s bytes uploaded' % (str(bytes_sent), str(total_bytes)))

    print('Upload chunks complete.')
    upload_finalize(oauth,media_id,upload_endpoint)

def upload_finalize(oauth,media_id,upload_endpoint):
    '''
    Finalizes uploads and starts video processing
    '''
    print('FINALIZE')

    request_data = {
      'command': 'FINALIZE',
      'media_id': media_id
    }

    req = requests.post(url=upload_endpoint, data=request_data, auth=oauth)
    print(req.json())

    processing_info = req.json().get('processing_info', None)
    check_status(processing_info,media_id,upload_endpoint,oauth)

def check_status(processing_info,media_id,upload_endpoint,oauth):

    if processing_info is None:
      return

    state = processing_info['state']

    print('Media processing status is %s ' % state)

    if state == u'succeeded':
      return

    if state == u'failed':
      print('Upload failed')
      return

    check_after_secs = processing_info['check_after_secs']
    
    print('Checking after %s seconds' % str(check_after_secs))
    time.sleep(check_after_secs)

    print('STATUS')

    request_params = {
      'command': 'STATUS',
      'media_id': media_id
    }

    req = requests.get(url=upload_endpoint, params=request_params, auth=oauth)
    
    processing_info = req.json().get('processing_info', None)
    check_status(processing_info,media_id,upload_endpoint,oauth)

def download_image(url):
    while True:
        try:
            image = requests.get(url).content
        except requests.RequestError: 
            time.sleep(2 * 60)
        else:
            break
    with open('tmp_photo.jpg', 'wb') as f:
        f.write(image) 

def download_video(url):
    while True:
        try:
            video = requests.get(url).content
        except requests.RequestError: 
            time.sleep(2 * 60)
        else:
            break
    with open('tmp_video.mp4', 'wb') as f:
        f.write(video)

def save_message_to_db(telegram_msg_id, telegram_msg_content, twitter_msg_id):
    conn = sqlite3.connect('messages.db')
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO messages (telegram_msg_id, telegram_msg_content, twitter_msg_id)
    VALUES (?, ?, ?)
    ''', (telegram_msg_id, telegram_msg_content, twitter_msg_id))
    conn.commit()
    conn.close()

def dosend(text,type="text",media_ids=None,reply_to_status_id=None):
        request_data={}
        if reply_to_status_id != None:
                request_data = {"text": text, "reply":{ "in_reply_to_tweet_id": reply_to_status_id}}
        else:
                request_data = {"text": text}
        
        if type == "image" or type == "video":
            request_data['media'] = {"media_ids": media_ids} 

        oauth = OAuth1Session(config.CONSUMER_API_KEY,
                              client_secret=config.CONSUMER_API_KEY_SECRET,
                              resource_owner_key=config.ACCESS_TOKEN,
                              resource_owner_secret=config.ACCESS_TOKEN_SECRET)

        response = oauth.post("https://api.twitter.com/2/tweets", json=request_data)

        return response
def get_twitter_id_for_reply(telegram_msg_id):
    conn = sqlite3.connect('messages.db')
    cursor = conn.cursor()
    cursor.execute('''
    SELECT twitter_msg_id FROM messages WHERE telegram_msg_id = ?
    ''', (telegram_msg_id,))
    twitter_msg_id = cursor.fetchone()
    conn.close()
    return str(twitter_msg_id[0]) if twitter_msg_id else None
async def send_tweet(update, context):
    type="text"
     # Distinguishing between a group message and a channel post
    if update.message:
        message_data = update.message
    elif update.channel_post:
        message_data = update.channel_post
    else:
        return

    text = message_data.text or message_data.caption

    original_telegram_msg_id = None
    if update.message and update.message.reply_to_message:
        original_telegram_msg_id = update.message.reply_to_message.message_id
    elif update.channel_post and update.channel_post.reply_to_message:
        original_telegram_msg_id = update.channel_post.reply_to_message.message_id 

    messages = split_message(text, 270)

    media_ids = []
    if update.channel_post and update.channel_post.photo:
        type="image"
        largest_photo: PhotoSize = max(update.channel_post.photo, key=lambda p: p.file_size)
        file = await context.bot.get_file(largest_photo.file_id)
        #file_path = file.download(custom_path="tmp_photo.jpg")
        download_image(file.file_path)
        media_id = get_images_id()
        media_ids.append(str(media_id))
    elif update.channel_post and update.channel_post.video:
        type="video"
        video: Video = update.channel_post.video
        file = await context.bot.get_file(video.file_id)
        download_video(file.file_path)
        media_id = get_video_id()
        media_ids.append(str(media_id))
    elif update.message and update.message.photo:
        type="image"
        largest_photo: PhotoSize = max(update.message.photo, key=lambda p: p.file_size)
        file = await context.bot.get_file(largest_photo.file_id)
        #file_path = file.download(custom_path="tmp_photo.jpg")
        download_image(file.file_path)
        media_id = get_images_id()
        media_ids.append(str(media_id))
    elif update.message and update.message.video:
        type="video"
        video: Video = update.message.video
        file = await context.bot.get_file(video.file_id)
        download_video(file.file_path)
        media_id = get_video_id()
        media_ids.append(str(media_id))

    if len(media_ids) == 0:
        media_ids = None

    twitter_reply_to_msg_id = None
    if original_telegram_msg_id:
        twitter_reply_to_msg_id = get_twitter_id_for_reply(original_telegram_msg_id)


    response = dosend(messages[0], type, media_ids, reply_to_status_id=twitter_reply_to_msg_id)
    previous_tweet_id = json.loads(response.text)['data']['id']
    if update.message:
        save_message_to_db(update.message.message_id, text, previous_tweet_id)
    elif update.channel_post:
        save_message_to_db(update.channel_post.message_id, text, previous_tweet_id)


    # Continue the thread with remaining parts of the message
    for msg in messages[1:]:
        response = dosend(msg,"text",None,reply_to_status_id=previous_tweet_id)
        previous_tweet_id = json.loads(response.text)['data']['id']

def cleanup_old_messages():
    one_month_ago = datetime.now() - timedelta(days=30)
    conn = sqlite3.connect('messages.db')
    cursor = conn.cursor()
    cursor.execute('''
    DELETE FROM messages WHERE timestamp < ?
    ''', (one_month_ago,))
    conn.commit()
    conn.close()

async def echo(update, context):
    print(update)

def main() -> None:
    setup_database()
    cleanup_old_messages()
    application = Application.builder().token(config.TELEGRAM_BOT_API_KEY).build()

    application.add_handler(MessageHandler(filters.Chat(config.TELEGRAM_CHANNEL_ID), send_tweet), group=-2)
    

    group_ids = [config.YOUR_GROUP_ID_1]  
    for group_id in group_ids:
        application.add_handler(MessageHandler(filters.Chat(group_id), send_tweet), group=-2)


    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
