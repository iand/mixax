import base64
import os
import os.path
import simplejson as json
import urlparse
import urllib
import urllib2
import hashlib
import contextlib
import db
import redis
import time
import base64
import hmac
import json

from flask import Flask, request, redirect, render_template, make_response, abort

FBAPI_APP_ID = os.environ.get('FACEBOOK_APP_ID')
FBAPI_APP_SECRET = os.environ.get('FACEBOOK_SECRET')

def connect_redis():
    return redis.StrictRedis(host=app.config["REDIS_HOST"], port=app.config["REDIS_PORT"], password=app.config["REDIS_PASSWORD"])

def urlsafe_b64decode(str):
    """Perform Base 64 decoding for strings with missing padding."""

    l = len(str)
    pl = l % 4
    return base64.urlsafe_b64decode(str.ljust(l+pl, "="))


def parse_signed_request(signed_request, secret):
    """
Parse signed_request given by Facebook (usually via POST),
decrypt with app secret.

Arguments:
signed_request -- Facebook's signed request given through POST
secret -- Application's app_secret required to decrpyt signed_request
"""

    if "." in signed_request:
        esig, payload = signed_request.split(".")
    else:
        return {}

    sig = urlsafe_b64decode(str(esig))
    data = json.loads(urlsafe_b64decode(str(payload)))

    if not isinstance(data, dict):
        raise SignedRequestError("Pyload is not a json string!")
        return {}

    if data["algorithm"].upper() == "HMAC-SHA256":
        if hmac.new(secret, payload, hashlib.sha256).digest() == sig:
            return data

    else:
        raise SignedRequestError("Not HMAC-SHA256 encrypted!")

    return {}



def get_user_from_cookie():
    """Parses the cookie set by the official Facebook JavaScript SDK.

cookies should be a dictionary-like object mapping cookie names to
cookie values.

If the user is logged in via Facebook, we return a dictionary with the
keys "uid" and "access_token". The former is the user's Facebook ID,
and the latter can be used to make authenticated requests to the Graph API.
If the user is not logged in, we return None.

Download the official Facebook JavaScript SDK at
http://github.com/facebook/connect-js/. Read more about Facebook
authentication at http://developers.facebook.com/docs/authentication/.
"""
    app_id = os.environ.get('FACEBOOK_APP_ID')
    app_secret = os.environ.get('FACEBOOK_SECRET')

    cookie = request.cookies.get("fbsr_" + app_id, "")
    if not cookie:
        return None

    response = parse_signed_request(cookie, app_secret)
    if not response:
        return None

    args = dict(
        code = response['code'],
        client_id = app_id,
        client_secret = app_secret,
        redirect_uri = '',
    )

    file = urllib.urlopen("https://graph.facebook.com/oauth/access_token?" + urllib.urlencode(args))
    try:
        token_response = file.read()
    finally:
        file.close()

    vals = urlparse.parse_qs(token_response)
    if 'access_token' in vals:
        access_token = urlparse.parse_qs(token_response)["access_token"][-1]

        return dict(
            uid = response["user_id"],
            access_token = access_token,
        )
    
    return None

def get_access_token():
    info = get_user_from_cookie()
    if info and 'access_token' in info:
        return info['access_token']
    else:
        return None


def get_entry_part(parent, entrynum, partnum):
    if parent is None:
        return ""
    else:
        return parent.entries[entrynum][partnum]


def fql(fql, token, args=None):
    if not args:
        args = {}

    args["query"], args["format"], args["access_token"] = fql, "json", token
    return json.loads(
        urllib2.urlopen("https://api.facebook.com/method/fql.query?" +
                        urllib.urlencode(args)).read())


def fb_call(call, args=None):
    return json.loads(urllib2.urlopen("https://graph.facebook.com/" + call +
                                      '?' + urllib.urlencode(args)).read())

app = Flask(__name__)
app.config.from_object(__name__)
app.config.from_object('conf.Config')

def get_top_three_artists(playlist):
    artists = {}

    for track, artist in playlist.entries:
        artists[artist] = artists.get(artist, 0) + 1
    
    keys, values = zip(*artists.items())
    items = zip(values, keys).sort(reverse=True)[:3]

    return zip(*items)[1]

@app.route('/', methods=['GET', 'POST'])
def index():
    me = app_friends = access_token = None
    access_token = get_access_token()
    if access_token:
        me = fb_call('me', args={'access_token': access_token})
        app_friends = fql(
            "SELECT uid, name, is_app_user, pic_square "
            "FROM user "
            "WHERE uid IN (SELECT uid2 FROM friend WHERE uid1 = me()) AND "
            "  is_app_user = 1", access_token)

    r = connect_redis()

    playlists = db.get_recent_playlists(r, 0, 100)
    playlists.sort(key=lambda playlist: playlist.score, reverse=True)
    playlists = playlists[:20]

    resp = make_response(render_template(
        'index.html', appId=FBAPI_APP_ID, app_friends=app_friends, me=me, access_token=access_token, recent_playlists=playlists, get_top_three_artists=get_top_three_artists))
    

    return resp
    


@app.route('/create/', defaults={"parent": None}, methods=['GET', 'POST'])
@app.route('/create/<int:parent>/', methods=['GET', 'POST'])
def newplaylist(parent):
    me = None
    access_token = get_access_token()
    if access_token:
        me = fb_call('me', args={'access_token': access_token})

    r = connect_redis()


    if request.method == "POST":
        entries = [
            (request.form["track1"], request.form["artist1"]),
            (request.form["track2"], request.form["artist2"]),
            (request.form["track3"], request.form["artist3"]),
            (request.form["track4"], request.form["artist4"]),
            (request.form["track5"], request.form["artist5"]),
            (request.form["track6"], request.form["artist6"]),
            (request.form["track7"], request.form["artist7"]),
        ]

        playlist = db.Playlist.new(r)
        playlist.userid = me["id"]
        playlist.title = request.form["title"]
        playlist.entries = entries
        playlist.genre_name = request.form["genre"] or "other"

        parent = request.form.get("parent", None)
        if parent:
            playlist.parent = int(parent)

        playlist.save()
        db.Genre.get(r, playlist.genre_name).add_playlist(playlist.id)

        resp = make_response(redirect("/playlist/%d/" % playlist.id))
    
        return resp

    parent_playlist = None
    if parent is not None:
        parent_playlist = db.Playlist.get(r, parent)

    genres = db.Genre.list(r)

    resp = make_response(render_template(
        'newplaylist.html', appId=FBAPI_APP_ID, me=me, access_token=access_token, parent=parent_playlist, get_entry_part=get_entry_part, genres=genres))
    
    return resp

@app.route("/playlist/<int:id>/", methods=["GET"])
def showplaylist(id):
    me = None
    access_token = get_access_token()
    if access_token:
        me = fb_call('me', args={'access_token': access_token})

    r = connect_redis()

    playlist = db.Playlist.get(r, id)
    if playlist is None:
        abort(404)
    
    resp = make_response(render_template(
        'showplaylist.html', appId=FBAPI_APP_ID, me=me, access_token=access_token, playlist=playlist))
    
    return resp

@app.route("/recent/", defaults={"page": 1}, methods=["GET"])
@app.route("/recent/<int:page>", methods=["GET"])
def recent(page):
    me = None
    access_token = get_access_token()
    if access_token:
        me = fb_call('me', args={'access_token': access_token})

    r = connect_redis()

    results_per_page = 20
    start = (page - 1) * results_per_page
    playlists = db.get_recent_playlists(r, start, results_per_page)

    resp = make_response(render_template("recent.html", appId=FBAPI_APP_ID, me=me, access_token=access_token, page=page, playlists=playlists, get_top_three_artists=get_top_three_artists))

    return resp

@app.route("/genre/<genre_name>/", methods=["GET"])
def show_genre(genre_name):
    me = None
    access_token = get_access_token()
    if access_token:
        me = fb_call('me', args={'access_token': access_token})

    r = connect_redis()

    playlists = db.get_recent_playlists(r, 0, 100, db.Genre.get(r, genre_name))
    playlists.sort(key=lambda playlist: playlist.score, reverse=True)
    playlists = playlists[:20]

    resp = make_response(render_template(
        'genre.html', appId=FBAPI_APP_ID, me=me, access_token=access_token, recent_playlists=playlists, get_top_three_artists=get_top_three_artists))
    

    return resp

@app.errorhandler(404)
def handle_404(error):
    me = None
    access_token = get_access_token()
    if access_token:
        me = fb_call('me', args={'access_token': access_token})
        r = connect_redis()

        return render_template("404.html", appId=FBAPI_APP_ID, me=me, access_token=access_token), 404
    
    else:
        return render_template("404.html"), 404

#@app.route("/testredis/", methods=["GET"])
#def testredis():
#    r = connect_redis()
#    v = r.incr("test")
#    return str(v)

@app.route('/close/', methods=['GET', 'POST'])
def close():
    return render_template('close.html')

@app.route("/api/add_score")
def api_add_score():
    d = get_user_from_cookie()
    uid = d["uid"]
    r = connect_redis()

    relscore = int(request.args["relscore"]) > 0 and 1 or -1
    plid = int(request.args["plid"])

    playlist = db.Playlist.get(r, plid)
    playlist.score -= r.srem("playlist:%d:thumbs_up" % plid, uid)   # take off removed positives
    playlist.score += r.srem("playlist:%d:thumbs_down" % plid, uid) # add on removed negatives
    playlist.score += relscore
    r.sadd("playlist:%d:thumbs_%s" % (plid, relscore > 0 and "up" or "down"), uid)

    playlist.save()

    return ""

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    if app.config.get('FBAPI_APP_ID') and app.config.get('FBAPI_APP_SECRET'):
        app.run(host='0.0.0.0', port=port)
    else:
        print 'Cannot start application without Facebook App Id and Secret set'
