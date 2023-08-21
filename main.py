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
POST_TWEET_URL = "https://api.twitter.com/1.1/statuses/update.json"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

def split_message(text, max_len):
    """Split the text into chunks of max_len, but not breaking in the middle of a word."""
    words = text.split()
    chunks, chunk = [], ""
    for word in words:
        if len(chunk) + len(word) > max_len:
            chunks.append(chunk)
            chunk = word
        else:
            chunk += " " + word
    if chunk:
        chunks.append(chunk)
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

async def send_tweet(update, context):
    type="text"
    text = update.channel_post.text

    if text == None:
        text = update.channel_post.caption

    messages = split_message(text, 270)

    media_ids = []
    if update.channel_post.photo:
        type="image"
        largest_photo: PhotoSize = max(update.channel_post.photo, key=lambda p: p.file_size)
        file = await context.bot.get_file(largest_photo.file_id)
        #file_path = file.download(custom_path="tmp_photo.jpg")
        download_image(file.file_path)
        media_id = get_images_id()
        media_ids.append(str(media_id))
    elif update.channel_post.video:
        type="video"
        video: Video = update.channel_post.video
        file = await context.bot.get_file(video.file_id)
        download_video(file.file_path)
        media_id = get_video_id()
        media_ids.append(str(media_id))

    if len(media_ids) == 0:
        media_ids = None

    response = dosend(messages[0],type,media_ids)

    previous_tweet_id = json.loads(response.text)['data']['id']

    # Continue the thread with remaining parts of the message
    for msg in messages[1:]:
        response = dosend(msg,"text",None,reply_to_status_id=previous_tweet_id)
        previous_tweet_id = json.loads(response.text)['data']['id']

def main() -> None:
    application = Application.builder().token(config.TELEGRAM_BOT_API_KEY).build()

    application.add_handler(MessageHandler(filters.Chat(config.TELEGRAM_CHANNEL_ID), send_tweet), group=-2)
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
