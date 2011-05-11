import twitter
from twitter import Api
import urllib2
import simplejson

class Tweets:

    def authentification(self, conf):
        self.api = ApiPatch(conf.consumer_key,
                conf.consumer_secret,
                conf.oauth_token,
                conf.oauth_token_secret)

    def updateHomeTimeline (self):
        ''' include_entities return some varius metadata in a structure, not use
        yet, but it might be usefull
        '''
        try:
            statuses = self.api.GetFriendsTimeline(retweets=True)
            return statuses
        except urllib2.URLError:
            print 'Could\'t get statuses, network is down ?'

    def postTweet (self, tweet, reply_to=None):
        self.api.PostUpdate(tweet)
        
    def retweet (self, id):
        self.api.PostRetweet(id)

class ApiPatch (Api):
    def PostRetweet(self, id):
        '''This code come from issue #130 on python-twitter tracker

        Retweet a tweet with the Retweet API

        The twitter.Api instance must be authenticated.

        Args:
        id: The numerical ID of the tweet you are retweeting

        Returns:
        A twitter.Status instance representing the retweet posted
        '''
        if not self._oauth_consumer:
            raise TwitterError("The twitter.Api instance must be authenticated.")
        try:
            if int(id) <= 0:
                raise TwitterError("'id' must be a positive number")
        except ValueError:
            raise TwitterError("'id' must be an integer")
        url = 'http://api.twitter.com/1/statuses/retweet/%s.json' % id
        json = self._FetchUrl(url, post_data={'dummy': None})
        data = simplejson.loads(json)
        self._CheckForTwitterError(data)
#        return Status.NewFromJsonDict(data)
