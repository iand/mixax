import time

def encode_entries(entries):
	return "|".join(reduce(lambda a, b: a + b, entries))

def decode_entries(s):
	parts = s.split("|")
	entries = []

	for i in range(len(parts) / 2):
		entries.append(parts[i*2:(i+1)*2])
	
	return entries

class Genre(object):
	@classmethod
	def get(cls, r, name):
		if r.get("genre:%s:textualName" % name) is None:
			return None
		
		textual_name = r.get("genre:%s:textualName" % name)

		return cls(r, name, textual_name)
	
	@classmethod
	def list(cls, r):
		genres = []

		for name in r.smembers("global:genres"):
			genres.append(Genre.get(r, name))
		
		return genres

	def __init__(self, r, name, textual_name):
		self.r = r
		self.name = name
		self.textual_name = textual_name
	
	def add_playlist(self, id):
		self.r.zadd("genre:%s:playlists" % self.name, id, id)
	
	def remove_playlist(self, id):
		self.r.zrem("genre:%s:playlists" % self.name, id)

class Playlist(object):
	#userid = title = entries = timestamp = None

	@classmethod
	def get(cls, r, id):
		if r.get("playlist:%d:userid" % id) is None:
			return None
		
		userid = int(r.get("playlist:%d:userid" % id))
		title = r.get("playlist:%d:title" % id)
		entries = decode_entries(r.get("playlist:%d:entries" % id))
		parent = int(r.get("playlist:%d:parent" % id))
		genre_name = r.get("playlist:%d:genre" % id)
		score = int(r.get("playlist:%d:score" % id))
		# ********************************************************************* Insert new fields here
		timestamp = float(r.zrank("global:recentPlaylists", id))

		# vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv Insert new fields here
		return cls(r, id, userid, title, entries, parent, genre_name, score, timestamp)
	
	@classmethod
	def new(cls, r):
		id = r.incr("global:nextPlaylistID")

		# vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv Insert new fields here
		return cls(r, id, 0, "", [], 0, "", 0, time.time())

	# vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv Insert new fields here
	def __init__(self, r, id, userid, title, entries, parent, genre_name, score, timestamp):
		self.r = r
		self.id = id
		self.userid = userid
		self.title = title
		self.entries = entries
		self.parent = parent
		self._parent_playlist = None
		self.genre_name = genre_name
		self.score = score
		# ********************************************************************* Insert new fields here
		self.timestamp = timestamp

	@property
	def genre(self):
		#self.title += "\n\ngenre_name: %s" % self.genre_name
		return Genre.get(self.r, self.genre_name)

	@property
	def parent_playlist(self):
		if self._parent_playlist is None:
			self._parent_playlist = Playlist.get(self.r, self.parent)
		
		return self._parent_playlist

	def save(self):
		self.r.set("playlist:%d:userid" % self.id, self.userid)
		self.r.set("playlist:%d:title" % self.id, self.title)
		self.r.set("playlist:%d:entries" % self.id, encode_entries(self.entries))
		self.r.set("playlist:%d:parent" % self.id, self.parent)
		self.r.set("playlist:%d:genre" % self.id, self.genre_name)
		self.r.set("playlist:%d:score" % self.id, self.score)
		# ********************************************************************* Insert new fields here
		self.r.zadd("global:recentPlaylists", self.timestamp, self.id)
	
	def delete(self):
		self.r.delete("playlist:%d:userid" % self.id)
		self.r.delete("playlist:%d:title" % self.id)
		self.r.delete("playlist:%d:entries" % self.id)
		self.r.delete("playlist:%d:parent" % self.id)
		self.r.delete("playlist:%d:genre" % self.id)
		self.r.delete("playlist:%d:score" % self.id)
		# ********************************************************************* Insert new fields here
		self.r.zrem("global:recentPlaylists", self.id)
	
	def __repr__(self):
		return "<Playlist '%s'>" % self.title

def get_recent_playlists(r, start=0, count=10, genre=None):
	key = "global:recentPlaylists"
	if genre is not None:
		key = "genre:%s:playlists" % genre.name

	ids = r.zrevrange(key, start, start + count)
	playlists = []

	for id in ids:
		playlists.append(Playlist.get(r, int(id)))
	
	return playlists