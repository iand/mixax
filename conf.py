import os


class Config(object):
    DEBUG = True
    TESTING = False
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'DEBUG')
    FBAPI_SCOPE = ['user_likes', 'user_photos',
                   'user_photo_video_tags']
    FBAPI_APP_ID = os.environ.get('FACEBOOK_APP_ID')
    FBAPI_APP_SECRET = os.environ.get('FACEBOOK_SECRET')

    REDIS_HOST = "dogfish.redistogo.com"
    REDIS_PORT = 9269
    REDIS_PASSWORD = "707d1b6b6ff05544cb4c9b896c314555"